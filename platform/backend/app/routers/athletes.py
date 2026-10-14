"""Sporcu & veli yönetimi (personel tarafı)."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from ..core.audit import audit
from ..core.crypto import encrypt
from ..core.db import db
from ..core.deps import Coaching, Staff, User, assert_guardian_owns_athlete
from ..core.timeutil import as_dt
from ..domain.billing import sibling_discount_pct
from ..domain.performance import decimal_age, maturity_band, maturity_offset
from ..schemas.common import Page
from ..schemas.people import AthleteCreate, AthleteOut, AthleteUpdate

router = APIRouter(prefix="/athletes", tags=["Sporcular"])


@router.get("", response_model=Page[AthleteOut])
async def list_athletes(
    _: Staff,
    q: str | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    team_id: Annotated[str | None, Query(alias="teamId")] = None,
    skip: int = Query(0, ge=0),
    take: int = Query(50, ge=1, le=200),
):
    where: dict = {}
    if status_:
        where["status"] = status_
    if q:
        where["OR"] = [
            {"firstName": {"contains": q, "mode": "insensitive"}},
            {"lastName": {"contains": q, "mode": "insensitive"}},
        ]
    if team_id:
        where["memberships"] = {"some": {"teamId": team_id, "leftOn": None}}
    items, total = (
        await db.athlete.find_many(
            where=where, skip=skip, take=take, order=[{"lastName": "asc"}, {"firstName": "asc"}]
        ),
        await db.athlete.count(where=where),
    )
    return Page(items=items, total=total, skip=skip, take=take)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_athlete(body: AthleteCreate, user: Coaching):
    """Doğrudan kayıt (lead'siz). Veli telefonla eşleşir; kardeş indirimi otomatik."""
    from ..services.crm import normalize_phone

    g_in = body.guardian
    phone = normalize_phone(g_in.phone)
    async with db.tx() as tx:
        g = await tx.guardian.find_first(where={"phone": phone})
        if g is None:
            g = await tx.guardian.create(
                data={
                    "firstName": g_in.firstName,
                    "lastName": g_in.lastName,
                    "phone": phone,
                    "email": g_in.email,
                    "billingAddress": g_in.billingAddress,
                    "taxIdEncrypted": encrypt(g_in.taxId) if g_in.taxId else None,
                }
            )
        siblings = await tx.athleteguardian.count(
            where={"guardianId": g.id, "athlete": {"is": {"status": {"in": ["ACTIVE", "TRIAL"]}}}}
        )
        a = await tx.athlete.create(
            data={
                **body.model_dump(include={"firstName", "lastName", "gender", "position", "dominantHand", "licenseNo"}),
                "birthDate": as_dt(body.birthDate),
                "joinedOn": as_dt(body.startsOn),
            }
        )
        await tx.athleteguardian.create(
            data={"athleteId": a.id, "guardianId": g.id, "relation": g_in.relation, "isBillingContact": True}
        )
        await tx.teammembership.create(
            data={"athleteId": a.id, "teamId": body.teamId, "joinedOn": as_dt(body.startsOn)}
        )
        disc = sibling_discount_pct(siblings + 1)
        await tx.subscription.create(
            data={
                "athleteId": a.id,
                "feePlanId": body.feePlanId,
                "startsOn": as_dt(body.startsOn),
                "discountPct": disc,
                "discountReason": "SIBLING" if disc else "NONE",
            }
        )
    await audit(user.id, "athlete.create", "Athlete", a.id)
    return {"id": a.id, "guardianId": g.id, "siblingDiscountPct": str(disc)}


@router.get("/{athlete_id}")
async def get_athlete(athlete_id: str, user: User):
    await assert_guardian_owns_athlete(user, athlete_id)
    a = await db.athlete.find_unique(
        where={"id": athlete_id},
        include={
            "guardians": {"include": {"guardian": True}},
            "memberships": {"where": {"leftOn": None}, "include": {"team": True}},
            "subscriptions": {"where": {"status": "ACTIVE"}, "include": {"feePlan": True}},
        },
    )
    if a is None:
        raise HTTPException(404, "Sporcu bulunamadı")
    return a


@router.patch("/{athlete_id}")
async def update_athlete(athlete_id: str, body: AthleteUpdate, user: Coaching):
    data = body.model_dump(exclude_none=True)
    if "medicalClearanceUntil" in data:
        data["medicalClearanceUntil"] = as_dt(data["medicalClearanceUntil"])
    if data.get("status") == "LEFT":
        data["leftOn"] = as_dt(date.today())
        # Ayrılan sporcunun aboneliği biter, açık üyeliği kapanır → gelecek ay tahakkuk oluşmaz.
        await db.subscription.update_many(
            where={"athleteId": athlete_id, "status": "ACTIVE"},
            data={"status": "ENDED", "endsOn": as_dt(date.today())},
        )
        await db.teammembership.update_many(
            where={"athleteId": athlete_id, "leftOn": None}, data={"leftOn": as_dt(date.today())}
        )
    a = await db.athlete.update(where={"id": athlete_id}, data=data)
    await audit(user.id, "athlete.update", "Athlete", athlete_id, body.model_dump(mode="json", exclude_none=True))
    return a


@router.get("/{athlete_id}/attendance-trend")
async def attendance_trend(athlete_id: str, user: User, months: int = Query(6, ge=1, le=24)):
    """Aylık devam yüzdesi + sRPE yükü (grafik için)."""
    await assert_guardian_owns_athlete(user, athlete_id)
    return await db.query_raw(
        """
        SELECT to_char(date_trunc('month', s."startsAt"), 'YYYY-MM') AS month,
               COUNT(*)::int AS sessions,
               COUNT(*) FILTER (WHERE a."status" IN ('PRESENT', 'LATE'))::int AS attended,
               ROUND(100.0 * COUNT(*) FILTER (WHERE a."status" IN ('PRESENT', 'LATE')) / NULLIF(COUNT(*), 0), 1)::float8 AS rate,
               COALESCE(SUM(a."rpe" * EXTRACT(EPOCH FROM (s."endsAt" - s."startsAt")) / 60), 0)::int AS load_au
        FROM "TrainingSession" s
        JOIN "TeamMembership" tm ON tm."teamId" = s."teamId" AND tm."athleteId" = $1::uuid
             AND tm."joinedOn" <= s."startsAt"::date AND (tm."leftOn" IS NULL OR tm."leftOn" > s."startsAt"::date)
        LEFT JOIN "Attendance" a ON a."sessionId" = s."id" AND a."athleteId" = $1::uuid
        WHERE s."status" = 'COMPLETED' AND s."type" <> 'TRIAL'
          AND s."startsAt" >= date_trunc('month', now()) - make_interval(months => $2::int - 1)
        GROUP BY 1 ORDER BY 1
        """,
        athlete_id,
        months,
    )


@router.get("/{athlete_id}/maturity")
async def maturity(athlete_id: str, user: User):
    """Moore 2015 olgunlaşma ofseti → bio-banding grubu. Son boy/oturma boyu ölçümünden."""
    await assert_guardian_owns_athlete(user, athlete_id)
    a = await db.athlete.find_unique(where={"id": athlete_id})
    if a is None:
        raise HTTPException(404, "Sporcu bulunamadı")
    latest = {}
    for code in ("HEIGHT", "SITTING_HEIGHT"):
        r = await db.physicaltestresult.find_first(
            where={"athleteId": athlete_id, "testType": {"is": {"code": code}}}, order={"measuredAt": "desc"}
        )
        latest[code] = r
    if latest["HEIGHT"] is None:
        raise HTTPException(422, "Boy ölçümü yok")
    on = latest["HEIGHT"].measuredAt.date()
    age = decimal_age(a.birthDate.date(), on)
    try:
        off = maturity_offset(
            a.gender,
            age,
            float(latest["HEIGHT"].value),
            float(latest["SITTING_HEIGHT"].value) if latest["SITTING_HEIGHT"] else None,
        )
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {
        "age": age,
        "maturityOffsetYears": off,
        "ageAtPhv": round(age - off, 2),
        "band": maturity_band(off),
        "note": "±1 yıl hata payı; yalnızca gruplama amaçlı kullanın (Moore ve ark., 2015).",
    }
