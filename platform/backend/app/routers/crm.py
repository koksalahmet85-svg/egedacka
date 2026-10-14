"""Sosyal medya & CRM: kampanya, harcama, lead hunisi, deneme antrenmanı, dönüşüm."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..core.audit import audit
from ..core.db import db
from ..core.deps import Marketing, Staff
from ..core.timeutil import as_dt
from ..schemas.common import Page
from ..schemas.crm import ActivityIn, CampaignIn, ConvertIn, LeadIn, SpendImport, StageChange, TrialIn, TrialResult
from ..services import crm as svc
from ..services import dashboard

router = APIRouter(prefix="/crm", tags=["CRM & Pazarlama"])


@router.get("/campaigns")
async def campaigns(_: Marketing, active: bool | None = None):
    where = {"isActive": active} if active is not None else {}
    return await db.adcampaign.find_many(where=where, order={"name": "asc"})


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(body: CampaignIn, _: Marketing):
    data = body.model_dump(exclude_none=True)
    for k in ("startsOn", "endsOn"):
        if k in data:
            data[k] = as_dt(data[k])
    return await db.adcampaign.create(data=data)


@router.post("/ad-spend/import")
async def import_spend(body: SpendImport, _: Marketing):
    """Manuel / CSV harcama aktarımı (API senkronu olmayan platformlar için). Upsert."""
    for r in body.rows:
        values = {"spend": r.spend, "impressions": r.impressions, "clicks": r.clicks, "platformLeads": r.platformLeads}
        await db.adspenddaily.upsert(
            where={"campaignId_date": {"campaignId": r.campaignId, "date": as_dt(r.date)}},
            data={"create": {"campaignId": r.campaignId, "date": as_dt(r.date), **values}, "update": values},
        )
    dashboard.invalidate_cache()
    return {"upserted": len(body.rows)}


@router.get("/leads", response_model=Page[dict])
async def leads(
    _: Staff,
    stage: str | None = None,
    source: str | None = None,
    owner_id: Annotated[str | None, Query(alias="ownerId")] = None,
    q: str | None = None,
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
):
    where: dict = {}
    if stage:
        where["stage"] = stage
    if source:
        where["source"] = source
    if owner_id:
        where["ownerId"] = owner_id
    if q:
        where["OR"] = [{"parentName": {"contains": q, "mode": "insensitive"}}, {"phone": {"contains": q}}]
    items = await db.lead.find_many(
        where=where, skip=skip, take=take, order={"createdAt": "desc"}, include={"campaign": True, "owner": True}
    )
    return Page(items=[i.model_dump() for i in items], total=await db.lead.count(where=where), skip=skip, take=take)


@router.get("/leads/sla-breaches")
async def sla_breaches(_: Marketing, minutes: int = Query(15, ge=1)):
    """Hâlâ aranmamış lead'ler. Yanıt hızı dönüşümün en güçlü belirleyicilerinden biridir."""
    return await db.query_raw(
        """SELECT "id", "parentName", "phone", "source"::text, "createdAt",
                  (EXTRACT(EPOCH FROM (now() AT TIME ZONE 'UTC' - "createdAt")) / 60)::int AS waiting_min
           FROM "Lead" WHERE "stage" = 'NEW'
             AND "createdAt" < (now() AT TIME ZONE 'UTC') - make_interval(mins => $1::int)
           ORDER BY "createdAt" LIMIT 100""",
        minutes,
    )


@router.post("/leads", status_code=status.HTTP_201_CREATED)
async def create_lead(body: LeadIn, user: Staff):
    data = body.model_dump(exclude_none=True)
    data["phone"] = svc.normalize_phone(body.phone)
    dup = await db.lead.find_first(where={"phone": data["phone"], "stage": {"not_in": ["WON", "LOST"]}})
    if dup:
        raise HTTPException(409, detail={"message": "Bu numarayla açık lead var", "leadId": dup.id})
    if user.staff_id:
        data["ownerId"] = user.staff_id
    dashboard.invalidate_cache()
    return await db.lead.create(data=data)


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: str, _: Staff):
    lead = await db.lead.find_unique(
        where={"id": lead_id},
        include={
            "activities": {"order_by": {"createdAt": "desc"}},
            "trials": {"include": {"session": True}},
            "campaign": True,
        },
    )
    if lead is None:
        raise HTTPException(404, "Lead bulunamadı")
    return lead


@router.post("/leads/{lead_id}/stage")
async def change_stage(lead_id: str, body: StageChange, user: Staff):
    lead = await db.lead.find_unique(where={"id": lead_id})
    if lead is None:
        raise HTTPException(404, "Lead bulunamadı")
    if body.stage == "WON":
        raise HTTPException(422, "WON yalnızca /convert ile (sporcu + abonelik oluşturularak) verilir")
    try:
        lead = await svc.advance_stage(lead, body.stage, user.staff_id, body.note, body.lostReason)
    except svc.CrmError as e:
        raise HTTPException(409, str(e))
    dashboard.invalidate_cache()
    return lead


@router.post("/leads/{lead_id}/activities", status_code=status.HTTP_201_CREATED)
async def add_activity(lead_id: str, body: ActivityIn, user: Staff):
    lead = await db.lead.find_unique(where={"id": lead_id})
    if lead is None:
        raise HTTPException(404, "Lead bulunamadı")
    data: dict = {"leadId": lead_id, "type": body.type, "note": body.note}
    if user.staff_id:
        data["actorId"] = user.staff_id
    act = await db.leadactivity.create(data=data)
    # İlk temas (arama/WhatsApp) otomatik CONTACTED → speed-to-lead ölçülür.
    if lead.stage == "NEW" and body.type in ("CALL", "WHATSAPP", "EMAIL"):
        await svc.advance_stage(lead, "CONTACTED", user.staff_id, note="İlk temas")
    return act


@router.post("/leads/{lead_id}/trials", status_code=status.HTTP_201_CREATED)
async def book_trial(lead_id: str, body: TrialIn, user: Staff):
    session = await db.trainingsession.find_unique(
        where={"id": body.sessionId}, include={"trials": {"where": {"status": "BOOKED"}}}
    )
    if session is None or session.status != "SCHEDULED":
        raise HTTPException(404, "Uygun seans yok")
    if session.startsAt <= datetime.now(UTC):
        raise HTTPException(422, "Geçmiş seansa deneme yazılamaz")
    if len(session.trials or []) >= session.trialSeats:
        raise HTTPException(409, "Deneme kontenjanı dolu")
    booking = await db.trialbooking.create(data={"leadId": lead_id, "sessionId": body.sessionId})
    lead = await db.lead.find_unique(where={"id": lead_id})
    if lead and lead.stage in ("NEW", "CONTACTED", "LOST"):
        await svc.advance_stage(lead, "TRIAL_SCHEDULED", user.staff_id)
    return booking


@router.post("/trials/{booking_id}/result")
async def trial_result(booking_id: str, body: TrialResult, user: Staff):
    try:
        b = await svc.mark_trial(booking_id, body.status, body.coachRating, body.coachFeedback, user.staff_id)
    except svc.CrmError as e:
        raise HTTPException(404, str(e))
    dashboard.invalidate_cache()
    return b


@router.post("/leads/{lead_id}/convert", status_code=status.HTTP_201_CREATED)
async def convert(lead_id: str, body: ConvertIn, user: Staff):
    """Lead → kayıtlı sporcu. Atıf zinciri (kampanya → lead → sporcu → ödemeler) burada kurulur."""
    try:
        out = await svc.convert_lead(
            lead_id,
            athlete=body.athlete.model_dump(exclude_none=True),
            guardian=body.guardian.model_dump(exclude_none=True, exclude={"taxId"}),
            team_id=body.teamId,
            fee_plan_id=body.feePlanId,
            starts_on=body.startsOn,
            actor_staff_id=user.staff_id,
        )
    except svc.CrmError as e:
        raise HTTPException(409, str(e))
    await audit(user.id, "lead.convert", "Lead", lead_id, out)
    dashboard.invalidate_cache()
    return out


@router.get("/lost-reasons")
async def lost_reasons(_: Marketing, days: int = Query(90, ge=7, le=365)):
    return await db.query_raw(
        """SELECT COALESCE("lostReason", 'belirtilmedi') AS reason, COUNT(*)::int AS n
           FROM "Lead" WHERE "stage" = 'LOST' AND "updatedAt" >= (now() AT TIME ZONE 'UTC') - make_interval(days => $1::int)
           GROUP BY 1 ORDER BY n DESC""",
        days,
    )
