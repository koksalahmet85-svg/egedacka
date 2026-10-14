"""Sporcu & veli portalı. Her uç nokta satır bazlı yetkiyle kendi verisine kilitlidir."""

from fastapi import APIRouter, HTTPException

from ..core.db import db
from ..core.deps import User, assert_guardian_owns_athlete
from ..services import billing

router = APIRouter(prefix="/portal", tags=["Sporcu & Veli Portalı"])


@router.get("/children")
async def my_children(user: User):
    if user.role == "ATHLETE" and user.athlete_id:
        ids = [user.athlete_id]
    elif user.role == "GUARDIAN" and user.guardian_id:
        links = await db.athleteguardian.find_many(where={"guardianId": user.guardian_id})
        ids = [link.athleteId for link in links]
    else:
        raise HTTPException(403, "Portal yalnızca veli ve sporcular içindir")
    return await db.athlete.find_many(
        where={"id": {"in": ids}},
        include={"memberships": {"where": {"leftOn": None}, "include": {"team": True}}},
    )


@router.get("/children/{athlete_id}/reports")
async def reports(athlete_id: str, user: User):
    await assert_guardian_owns_athlete(user, athlete_id)
    # Veli yalnızca koçun yorumlayıp yayınladığı raporları görür.
    return await db.monthlyreport.find_many(
        where={"athleteId": athlete_id, "publishedAt": {"not": None}}, order={"period": "desc"}, take=24
    )


@router.get("/children/{athlete_id}/schedule")
async def schedule(athlete_id: str, user: User):
    await assert_guardian_owns_athlete(user, athlete_id)
    return await db.query_raw(
        """
        SELECT s."id", s."startsAt", s."endsAt", s."type"::text, s."focus", t."name" AS team,
               v."name" || ' / ' || c."name" AS court
        FROM "TrainingSession" s
        JOIN "TrainingPlan" p ON p."id" = s."planId" AND p."status" = 'PUBLISHED'
        JOIN "TeamMembership" tm ON tm."teamId" = s."teamId" AND tm."athleteId" = $1::uuid AND tm."leftOn" IS NULL
        JOIN "Team" t ON t."id" = s."teamId"
        JOIN "Court" c ON c."id" = s."courtId" JOIN "Venue" v ON v."id" = c."venueId"
        WHERE s."status" = 'SCHEDULED' AND s."startsAt" >= (now() AT TIME ZONE 'UTC')
          AND s."startsAt" < (now() AT TIME ZONE 'UTC') + interval '14 days'
        ORDER BY s."startsAt"
        """,
        athlete_id,
    )


@router.get("/billing")
async def my_billing(user: User):
    if user.role != "GUARDIAN" or not user.guardian_id:
        raise HTTPException(403, "Yalnızca veliler")
    st = await billing.guardian_statement(user.guardian_id)
    st["invoices"] = await db.invoice.find_many(
        where={"guardianId": user.guardian_id, "status": {"in": ["ISSUED", "SENT"]}},
        order={"issuedAt": "desc"},
        take=24,
    )
    return st
