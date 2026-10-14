"""Lead yaşam döngüsü: webhook alımı, aşama geçişleri, deneme antrenmanı, üyeliğe dönüşüm."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import date, datetime

import httpx

from prisma.models import Lead

from ..core.config import get_settings
from ..core.db import db
from ..core.timeutil import as_dt, utcnow
from ..domain.billing import sibling_discount_pct

STAGES = ["NEW", "CONTACTED", "TRIAL_SCHEDULED", "TRIAL_ATTENDED", "WON"]
MILESTONE_FIELD = {
    "CONTACTED": "firstContactAt",
    "TRIAL_SCHEDULED": "trialScheduledAt",
    "TRIAL_ATTENDED": "trialAttendedAt",
    "WON": "wonAt",
}


class CrmError(Exception):
    pass


def normalize_phone(raw: str) -> str:
    """TR numaralarını E.164'e çevirir: '0532 111 22 33' → '+905321112233'."""
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("90") and len(digits) == 12:
        return "+" + digits
    if digits.startswith("0") and len(digits) == 11:
        return "+9" + digits
    if len(digits) == 10 and digits.startswith("5"):
        return "+90" + digits
    return "+" + digits if digits else ""


def verify_hmac_sha256(secret: str, body: bytes, signature: str | None, prefix: str = "") -> bool:
    if not secret or not signature:
        return False
    expected = prefix + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def advance_stage(
    lead: Lead, to_stage: str, actor_staff_id: str | None, note: str | None = None, lost_reason: str | None = None
) -> Lead:
    """Geri gidişe izin verilmez (LOST'tan yeniden açma hariç). Kilometre taşları bir kez yazılır."""
    if to_stage == lead.stage:
        return lead
    if to_stage == "LOST":
        if not lost_reason:
            raise CrmError("LOST için kayıp nedeni zorunlu")
    elif lead.stage != "LOST" and STAGES.index(to_stage) < STAGES.index(lead.stage):
        raise CrmError(f"{lead.stage} → {to_stage} geri geçişe izin yok")

    now = utcnow()
    data: dict = {"stage": to_stage}
    if to_stage == "LOST":
        data["lostReason"] = lost_reason
    else:
        # Atlanan ara aşamaların kilometre taşlarını da doldur (ör. NEW → TRIAL_SCHEDULED telefonla).
        for st in STAGES[1 : STAGES.index(to_stage) + 1]:
            f = MILESTONE_FIELD[st]
            if getattr(lead, f) is None:
                data[f] = now
    activity: dict = {
        "leadId": lead.id,
        "type": "STAGE_CHANGE",
        "fromStage": lead.stage,
        "toStage": to_stage,
        "note": note,
    }
    if actor_staff_id:
        activity["actorId"] = actor_staff_id
    async with db.tx() as tx:
        updated = await tx.lead.update(where={"id": lead.id}, data=data)
        await tx.leadactivity.create(data=activity)
    assert updated is not None
    return updated


async def _ensure_campaign(platform: str, external_id: str | None, name: str | None) -> str | None:
    if not external_id:
        return None
    c = await db.adcampaign.upsert(
        where={"platform_externalId": {"platform": platform, "externalId": external_id}},
        data={"create": {"platform": platform, "externalId": external_id, "name": name or external_id}, "update": {}},
    )
    return c.id


async def ingest_meta_lead(leadgen_id: str) -> Lead:
    """Meta Lead Ads webhook'u yalnızca leadgen_id gönderir; detay Graph API'den çekilir."""
    existing = await db.lead.find_unique(where={"externalLeadId": leadgen_id})
    if existing:
        return existing
    s = get_settings()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"https://graph.facebook.com/v21.0/{leadgen_id}",
            params={"access_token": s.meta_access_token, "fields": "field_data,campaign_id,campaign_name,created_time"},
        )
        r.raise_for_status()
        data = r.json()
    fields = {f["name"]: (f.get("values") or [""])[0] for f in data.get("field_data", [])}
    campaign_id = await _ensure_campaign("META", data.get("campaign_id"), data.get("campaign_name"))
    birth_year = fields.get("cocuk_dogum_yili") or fields.get("child_birth_year")
    return await db.lead.create(
        data={
            "parentName": fields.get("full_name") or "Bilinmiyor",
            "phone": normalize_phone(fields.get("phone_number", "")),
            "email": fields.get("email"),
            "childName": fields.get("cocuk_adi") or fields.get("child_name"),
            "childBirthYear": int(birth_year) if birth_year and str(birth_year).isdigit() else None,
            "source": "META_LEAD_AD",
            "campaignId": campaign_id,
            "externalLeadId": leadgen_id,
            "utmSource": "meta",
            "marketingConsent": str(fields.get("pazarlama_izni", "")).lower() in ("true", "evet", "yes"),
        }
    )


async def find_or_create_lead(*, name: str, phone: str | None, email: str | None, source: str) -> Lead:
    phone_n = normalize_phone(phone) if phone else None
    or_: list[dict] = []
    if phone_n:
        or_.append({"phone": phone_n})
    if email:
        or_.append({"email": email})
    if or_:
        found = await db.lead.find_first(where={"OR": or_, "stage": {"not": "WON"}}, order={"createdAt": "desc"})
        if found:
            return found
    return await db.lead.create(data={"parentName": name, "phone": phone_n or "", "email": email, "source": source})


async def handle_calcom_booking(event: str, payload: dict) -> str:
    """Cal.com BOOKING_CREATED / BOOKING_CANCELLED / BOOKING_RESCHEDULED."""
    uid = payload.get("uid")
    if not uid:
        raise CrmError("booking uid yok")
    if event == "BOOKING_CANCELLED":
        n = await db.trialbooking.update_many(where={"calBookingUid": uid}, data={"status": "CANCELLED"})
        return f"cancelled:{n}"

    attendee = (payload.get("attendees") or [{}])[0]
    responses = payload.get("responses") or {}
    phone_resp = responses.get("phone") or responses.get("attendeePhoneNumber")
    if isinstance(phone_resp, dict):
        phone_resp = phone_resp.get("value")
    phone = attendee.get("phoneNumber") or phone_resp
    start = datetime.fromisoformat(payload["startTime"].replace("Z", "+00:00"))

    session = await db.trainingsession.find_first(
        where={"startsAt": start, "trialSeats": {"gt": 0}, "status": "SCHEDULED"},
        include={"trials": {"where": {"status": "BOOKED"}}},
    )
    if session is None:
        raise CrmError(f"{start.isoformat()} için deneme kontenjanlı seans yok")
    if len(session.trials or []) >= session.trialSeats:
        raise CrmError("deneme kontenjanı dolu")

    lead = await find_or_create_lead(
        name=attendee.get("name") or "Cal.com", phone=phone, email=attendee.get("email"), source="WEBSITE"
    )
    if event == "BOOKING_RESCHEDULED":
        old_uid = payload.get("rescheduleUid") or payload.get("fromReschedule")
        if old_uid:
            await db.trialbooking.update_many(where={"calBookingUid": old_uid}, data={"status": "CANCELLED"})
    await db.trialbooking.upsert(
        where={"leadId_sessionId": {"leadId": lead.id, "sessionId": session.id}},
        data={
            "create": {"leadId": lead.id, "sessionId": session.id, "calBookingUid": uid},
            "update": {"status": "BOOKED", "calBookingUid": uid},
        },
    )
    if lead.stage in ("NEW", "CONTACTED", "LOST"):
        await advance_stage(lead, "TRIAL_SCHEDULED", None, note="Cal.com rezervasyonu")
    return f"booked:{lead.id}"


async def mark_trial(booking_id: str, status: str, rating: int | None, feedback: str | None, staff_id: str | None):
    b = await db.trialbooking.update(
        where={"id": booking_id},
        data={"status": status, "coachRating": rating, "coachFeedback": feedback},
        include={"lead": True},
    )
    if b is None:
        raise CrmError("rezervasyon bulunamadı")
    if status == "ATTENDED" and b.lead and b.lead.stage in ("NEW", "CONTACTED", "TRIAL_SCHEDULED"):
        await advance_stage(b.lead, "TRIAL_ATTENDED", staff_id, note="Deneme antrenmanına katıldı")
    return b


async def convert_lead(
    lead_id: str,
    *,
    athlete: dict,
    guardian: dict,
    team_id: str,
    fee_plan_id: str,
    starts_on: date,
    actor_staff_id: str | None,
) -> dict:
    """Lead → Sporcu + Veli + Takım üyeliği + Abonelik. Tek transaction."""
    lead = await db.lead.find_unique(where={"id": lead_id})
    if lead is None:
        raise CrmError("lead bulunamadı")
    if lead.convertedAthleteId:
        raise CrmError("lead zaten dönüştürülmüş")

    guardian = dict(guardian)
    relation = guardian.pop("relation", "VELİ")
    phone = normalize_phone(guardian["phone"])
    async with db.tx() as tx:
        g = await tx.guardian.find_first(where={"phone": phone})
        if g is None:
            g = await tx.guardian.create(data={**guardian, "phone": phone})
        siblings = await tx.athleteguardian.count(
            where={"guardianId": g.id, "athlete": {"is": {"status": {"in": ["ACTIVE", "TRIAL"]}}}}
        )
        discount = sibling_discount_pct(siblings + 1)
        a = await tx.athlete.create(
            data={
                **athlete,
                "birthDate": as_dt(athlete["birthDate"]),
                "joinedOn": as_dt(starts_on),
                "status": "ACTIVE",
            }
        )
        await tx.athleteguardian.create(
            data={"athleteId": a.id, "guardianId": g.id, "relation": relation, "isBillingContact": True}
        )
        await tx.teammembership.create(data={"athleteId": a.id, "teamId": team_id, "joinedOn": as_dt(starts_on)})
        sub = await tx.subscription.create(
            data={
                "athleteId": a.id,
                "feePlanId": fee_plan_id,
                "startsOn": as_dt(starts_on),
                "discountPct": discount,
                "discountReason": "SIBLING" if discount > 0 else "NONE",
            }
        )
        await tx.lead.update(where={"id": lead.id}, data={"convertedAthleteId": a.id})
    await advance_stage(lead, "WON", actor_staff_id, note="Üyeliğe dönüştü")
    return {"athleteId": a.id, "guardianId": g.id, "subscriptionId": sub.id, "discountPct": str(discount)}
