"""Sosyal medya & CRM: lead, huni, deneme antrenmanı, kampanya harcaması, ROI."""
from datetime import UTC, date, datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.db import get_conn, rows
from ..core.security import CRM_ROLES, SPORT_ROLES, CurrentUser, Role, require
from ..services import dashboard
from ..services.notify import enqueue
from .athletes import AthleteIn, create_athlete_tx

router = APIRouter(prefix="/crm", tags=["crm"])
CHANNELS = "^(META_ADS|GOOGLE_ADS|TIKTOK_ADS|ORGANIC_SOCIAL|WEBSITE|REFERRAL|SCHOOL_EVENT|WALK_IN)$"
STAGES = "^(NEW|CONTACTED|TRIAL_SCHEDULED|TRIAL_ATTENDED|WON|LOST)$"


class LeadIn(BaseModel):
    child_name: str
    child_birth_year: int | None = Field(None, ge=2005, le=2022)
    guardian_name: str
    phone: str = Field(pattern=r"^\+90\d{10}$")
    email: str | None = None
    channel: str = Field(pattern=CHANNELS)
    campaign_id: int | None = None
    external_lead_id: str | None = None
    utm_source: str | None = None
    utm_medium: str | None = None
    utm_campaign: str | None = None
    utm_content: str | None = None
    click_id: str | None = None
    kvkk_consent: bool = False


class StageChange(BaseModel):
    stage: str = Field(pattern=STAGES)
    note: str | None = None
    lost_reason: str | None = None


class ActivityIn(BaseModel):
    type: str = Field(pattern="^(CALL|WHATSAPP|SMS|EMAIL|NOTE)$")
    note: str | None = None


class TrialIn(BaseModel):
    session_id: int


class TrialResult(BaseModel):
    status: str = Field(pattern="^(ATTENDED|NO_SHOW|CANCELLED)$")
    coach_feedback: str | None = None
    coach_rating: int | None = Field(None, ge=1, le=5)


class CampaignIn(BaseModel):
    name: str
    channel: str = Field(pattern=CHANNELS)
    external_id: str | None = None
    start_date: date
    end_date: date | None = None
    budget: float | None = None
    target_age_group: str | None = None


class SpendRow(BaseModel):
    campaign_id: int
    date: date
    spend: float = Field(ge=0)
    impressions: int = 0
    clicks: int = 0
    platform_leads: int = 0


async def upsert_lead(conn: asyncpg.Connection, data: LeadIn) -> tuple[int, bool]:
    """Lead kaydı + tekilleştirme. Aynı telefon 30 gün içinde tekrar gelirse yeni lead
    açılmaz, aktivite düşülür (çift sayım CPL'yi yapay olarak düşürür)."""
    if data.external_lead_id:
        existing = await conn.fetchval("SELECT id FROM leads WHERE external_lead_id=$1", data.external_lead_id)
        if existing:
            return existing, False
    dup = await conn.fetchval(
        """SELECT id FROM leads WHERE phone=$1 AND created_at > now() - interval '30 days'
           AND stage NOT IN ('WON','LOST') ORDER BY created_at DESC LIMIT 1""", data.phone)
    if dup:
        await conn.execute(
            "INSERT INTO lead_activities (lead_id, type, note) VALUES ($1,'NOTE',$2)",
            dup, f"Tekrar başvuru: {data.channel} / {data.utm_campaign or '-'}")
        return dup, False
    fields = data.model_dump(exclude={"kvkk_consent"})
    lead_id = await conn.fetchval(
        f"""INSERT INTO leads ({", ".join(fields)}, kvkk_consent_at)
            VALUES ({", ".join(f"${i + 1}" for i in range(len(fields)))}, CASE WHEN ${len(fields) + 1} THEN now() END)
            RETURNING id""", *fields.values(), data.kvkk_consent)
    # Speed-to-lead: ilk 5 dakikada dönüş dönüşümü belirgin artırır → anında karşılama mesajı.
    await enqueue(conn, "WHATSAPP", data.phone, "lead_welcome",
                  {"guardian": data.guardian_name, "child": data.child_name}, f"lead_welcome:{lead_id}")
    return lead_id, True


@router.post("/leads", status_code=201)
async def create_lead(data: LeadIn, _: CurrentUser = Depends(require(*CRM_ROLES)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    async with conn.transaction():
        lead_id, created = await upsert_lead(conn, data)
    return {"id": lead_id, "created": created}


@router.get("/leads")
async def list_leads(stage: str | None = None, campaign_id: int | None = None, owner_id: int | None = None,
                     stale_hours: int | None = Query(None, description="Bu kadar saattir dokunulmamış lead'ler"),
                     limit: int = Query(100, le=500), offset: int = 0,
                     _: CurrentUser = Depends(require(*CRM_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT l.*, c.name AS campaign_name,
                  (SELECT MAX(created_at) FROM lead_activities la WHERE la.lead_id = l.id) AS last_activity_at
           FROM leads l LEFT JOIN campaigns c ON c.id = l.campaign_id
           WHERE ($1::lead_stage IS NULL OR l.stage=$1) AND ($2::int IS NULL OR l.campaign_id=$2)
             AND ($3::int IS NULL OR l.owner_id=$3)
             AND ($4::int IS NULL OR (l.stage NOT IN ('WON','LOST') AND COALESCE(
                  (SELECT MAX(created_at) FROM lead_activities la WHERE la.lead_id = l.id), l.created_at)
                  < now() - make_interval(hours => $4)))
           ORDER BY l.created_at DESC LIMIT $5 OFFSET $6""",
        stage, campaign_id, owner_id, stale_hours, limit, offset))


@router.post("/leads/{lead_id}/activities", status_code=201)
async def add_activity(lead_id: int, data: ActivityIn, user: CurrentUser = Depends(require(*CRM_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """Temas kaydı. İlk temas first_contact_at'i set eder ve NEW → CONTACTED geçişini yapar."""
    async with conn.transaction():
        await conn.execute("INSERT INTO lead_activities (lead_id, type, note, staff_id) VALUES ($1,$2,$3,$4)",
                           lead_id, data.type, data.note, user.staff_id)
        if data.type != "NOTE":
            prev = await conn.fetchval(
                """UPDATE leads SET first_contact_at = COALESCE(first_contact_at, now()),
                       owner_id = COALESCE(owner_id, $2),
                       stage = CASE WHEN stage='NEW' THEN 'CONTACTED'::lead_stage ELSE stage END
                   WHERE id=$1 RETURNING stage""", lead_id, user.staff_id)
            if prev is None:
                raise HTTPException(404, "Lead yok")
    return {"ok": True}


@router.patch("/leads/{lead_id}/stage")
async def change_stage(lead_id: int, data: StageChange, user: CurrentUser = Depends(require(*CRM_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    if data.stage == "WON":
        raise HTTPException(422, "WON yalnız /convert ile (sporcu kaydı açılarak) verilir")
    if data.stage == "LOST" and not data.lost_reason:
        raise HTTPException(422, "Kayıp nedeni zorunlu (fiyat, mesafe, saat uyumu …) — kampanya optimizasyonu için")
    async with conn.transaction():
        prev = await conn.fetchval("SELECT stage FROM leads WHERE id=$1 FOR UPDATE", lead_id)
        if prev is None:
            raise HTTPException(404, "Lead yok")
        await conn.execute("UPDATE leads SET stage=$2, lost_reason=$3 WHERE id=$1", lead_id, data.stage, data.lost_reason)
        await conn.execute(
            """INSERT INTO lead_activities (lead_id, type, from_stage, to_stage, note, staff_id)
               VALUES ($1,'STAGE_CHANGE',$2,$3,$4,$5)""", lead_id, prev, data.stage, data.note, user.staff_id)
    return {"from": prev, "to": data.stage}


@router.post("/leads/{lead_id}/trials", status_code=201)
async def book_trial(lead_id: int, data: TrialIn, user: CurrentUser = Depends(require(*CRM_ROLES)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """Deneme antrenmanı: lead mevcut bir seansa eklenir (ayrı seans açılmaz → koç maliyeti yok)."""
    async with conn.transaction():
        s = await conn.fetchrow("SELECT starts_at, status FROM training_sessions WHERE id=$1", data.session_id)
        if not s or s["status"] != "PLANNED" or s["starts_at"] < datetime.now(UTC):
            raise HTTPException(422, "Seans planlı ve gelecekte olmalı")
        tid = await conn.fetchval("INSERT INTO trial_bookings (lead_id, session_id) VALUES ($1,$2) RETURNING id",
                                  lead_id, data.session_id)
        prev = await conn.fetchval(
            """UPDATE leads l SET stage='TRIAL_SCHEDULED', first_contact_at = COALESCE(first_contact_at, now())
               FROM (SELECT stage FROM leads WHERE id=$1) old WHERE l.id=$1 RETURNING old.stage""", lead_id)
        await conn.execute(
            """INSERT INTO lead_activities (lead_id, type, from_stage, to_stage, staff_id)
               VALUES ($1,'STAGE_CHANGE',$2,'TRIAL_SCHEDULED',$3)""", lead_id, prev, user.staff_id)
        phone = await conn.fetchval("SELECT phone FROM leads WHERE id=$1", lead_id)
        # Hatırlatma no-show oranını düşürür; gönderim zamanı worker'da (seanstan 24 saat önce).
        await enqueue(conn, "WHATSAPP", phone, "trial_booked",
                      {"starts_at": s["starts_at"].isoformat(), "trial_id": tid}, f"trial_booked:{tid}")
    return {"id": tid}


@router.patch("/trials/{trial_id}")
async def trial_result(trial_id: int, data: TrialResult, user: CurrentUser = Depends(require(*CRM_ROLES, *SPORT_ROLES)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """Koç deneme sonucunu girer. ATTENDED → lead TRIAL_ATTENDED; satış 48 saat içinde kapanışı arar."""
    async with conn.transaction():
        lead_id = await conn.fetchval(
            """UPDATE trial_bookings SET status=$2, coach_feedback=$3, coach_rating=$4 WHERE id=$1 RETURNING lead_id""",
            trial_id, data.status, data.coach_feedback, data.coach_rating)
        if lead_id is None:
            raise HTTPException(404, "Deneme kaydı yok")
        if data.status == "ATTENDED":
            prev = await conn.fetchval("SELECT stage FROM leads WHERE id=$1", lead_id)
            if prev not in ("WON", "LOST"):
                await conn.execute("UPDATE leads SET stage='TRIAL_ATTENDED' WHERE id=$1", lead_id)
                await conn.execute(
                    """INSERT INTO lead_activities (lead_id, type, from_stage, to_stage, staff_id, note)
                       VALUES ($1,'STAGE_CHANGE',$2,'TRIAL_ATTENDED',$3,$4)""",
                    lead_id, prev, user.staff_id, data.coach_feedback)
    return {"ok": True}


@router.post("/leads/{lead_id}/convert", status_code=201)
async def convert(lead_id: int, data: AthleteIn, _: CurrentUser = Depends(require(*CRM_ROLES)),
                  conn: asyncpg.Connection = Depends(get_conn)):
    """Lead → Sporcu + Veli + Abonelik (tek transaction). ROI atfı lead.athlete_id üzerinden kurulur."""
    lead = await conn.fetchrow("SELECT stage, athlete_id FROM leads WHERE id=$1", lead_id)
    if not lead:
        raise HTTPException(404, "Lead yok")
    if lead["athlete_id"]:
        raise HTTPException(409, "Lead zaten dönüştürülmüş")
    async with conn.transaction():
        athlete_id = await create_athlete_tx(conn, data, lead_id=lead_id)
        await conn.execute(
            """INSERT INTO lead_activities (lead_id, type, from_stage, to_stage, note)
               VALUES ($1,'STAGE_CHANGE',$2,'WON','Kayıt tamamlandı')""", lead_id, lead["stage"])
    return {"athlete_id": athlete_id}


@router.get("/campaigns")
async def campaigns(_: CurrentUser = Depends(require(*CRM_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch("SELECT * FROM campaigns ORDER BY start_date DESC"))


@router.post("/campaigns", status_code=201)
async def create_campaign(data: CampaignIn, _: CurrentUser = Depends(require(Role.ADMIN, Role.MARKETING)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO campaigns (name, channel, external_id, start_date, end_date, budget, target_age_group)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""", *data.model_dump().values())}


@router.put("/ad-spend")
async def upsert_spend(items: list[SpendRow], _: CurrentUser = Depends(require(Role.ADMIN, Role.MARKETING)),
                       conn: asyncpg.Connection = Depends(get_conn)):
    """Günlük reklam harcaması (Meta/Google Insights senkronu ya da CSV). Upsert → tekrar yüklemek güvenli."""
    await conn.executemany(
        """INSERT INTO ad_spend_daily (campaign_id, date, spend, impressions, clicks, platform_leads)
           VALUES ($1,$2,$3,$4,$5,$6)
           ON CONFLICT (campaign_id, date) DO UPDATE SET spend=EXCLUDED.spend, impressions=EXCLUDED.impressions,
             clicks=EXCLUDED.clicks, platform_leads=EXCLUDED.platform_leads""",
        [tuple(i.model_dump().values()) for i in items])
    return {"rows": len(items)}


@router.get("/funnel")
async def funnel(date_from: date | None = None, date_to: date | None = None,
                 _: CurrentUser = Depends(require(*CRM_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    """Kohort hunisi + aşama süreleri (medyan gün) + kayıp nedenleri."""
    d_from, d_to = (date_from, date_to) if date_from and date_to else dashboard.default_range()
    summary = await dashboard.executive_summary(d_from, d_to)
    timing = rows(await conn.fetch(
        """WITH t AS (
             SELECT l.id, l.created_at,
                    MIN(la.created_at) FILTER (WHERE la.to_stage='TRIAL_SCHEDULED') AS scheduled,
                    MIN(la.created_at) FILTER (WHERE la.to_stage='TRIAL_ATTENDED') AS attended,
                    l.converted_at
             FROM leads l LEFT JOIN lead_activities la ON la.lead_id = l.id
             WHERE l.created_at::date BETWEEN $1 AND $2 GROUP BY l.id)
           SELECT
             percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM scheduled - created_at)/86400)::float8 AS lead_to_trial_days,
             percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM converted_at - attended)/86400)::float8 AS trial_to_won_days
           FROM t""", d_from, d_to))
    lost = rows(await conn.fetch(
        """SELECT COALESCE(lost_reason,'(belirtilmemiş)') AS reason, COUNT(*) AS count FROM leads
           WHERE stage='LOST' AND created_at::date BETWEEN $1 AND $2 GROUP BY 1 ORDER BY 2 DESC""", d_from, d_to))
    return {"funnel": summary["marketing"]["funnel"], "timing": timing[0], "lost_reasons": lost}


@router.get("/roi")
async def roi(date_from: date | None = None, date_to: date | None = None,
              _: CurrentUser = Depends(require(*CRM_ROLES, Role.ACCOUNTANT))):
    d_from, d_to = (date_from, date_to) if date_from and date_to else dashboard.default_range()
    m = (await dashboard.executive_summary(d_from, d_to))["marketing"]
    return {k: v for k, v in m.items() if k != "funnel"}


@router.get("/trials/upcoming")
async def upcoming_trials(days: int = 7, _: CurrentUser = Depends(require(*CRM_ROLES, *SPORT_ROLES)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT tb.id, tb.status, l.child_name, l.child_birth_year, l.guardian_name, l.phone,
                  s.starts_at, t.name AS team_name, f.name AS facility
           FROM trial_bookings tb JOIN leads l ON l.id = tb.lead_id
           JOIN training_sessions s ON s.id = tb.session_id LEFT JOIN teams t ON t.id = s.team_id
           JOIN facilities f ON f.id = s.facility_id
           WHERE s.starts_at BETWEEN now() AND now() + make_interval(days => $1) ORDER BY s.starts_at""",
        days))
