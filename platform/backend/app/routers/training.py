"""Tesis, takım, haftalık dinamik program, seans ve yoklama."""

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from prisma.errors import UniqueViolationError

from ..core.db import db
from ..core.deps import Coaching, Management, Staff
from ..core.timeutil import as_dt, utcnow
from ..domain.scheduling import monday_of
from ..schemas.training import (
    AttendanceBulk,
    ConflictOut,
    CourtIn,
    DrillIn,
    GenerateWeek,
    GenerateWeekOut,
    SessionPatch,
    SlotIn,
    TeamIn,
    VenueIn,
)
from ..services import training as svc

router = APIRouter(prefix="/training", tags=["Takım & Antrenman"])


def _is_overlap_error(e: Exception) -> bool:
    msg = str(e)
    return "session_court_no_overlap" in msg or "session_coach_no_overlap" in msg


# ── Tesis ──
@router.get("/venues")
async def venues(_: Staff):
    return await db.venue.find_many(where={"isActive": True}, include={"courts": True})


@router.post("/venues", status_code=status.HTTP_201_CREATED)
async def create_venue(body: VenueIn, _: Management):
    return await db.venue.create(data=body.model_dump(exclude_none=True))


@router.post("/courts", status_code=status.HTTP_201_CREATED)
async def create_court(body: CourtIn, _: Management):
    return await db.court.create(data=body.model_dump(exclude_none=True))


@router.get("/courts/utilization")
async def court_utilization(_: Management, week_start: Annotated[date, Query(alias="weekStart")]):
    """Saha doluluk oranı (16:00-22:00 prime-time × 7 gün = 42 saat kapasite)."""
    lo = as_dt(monday_of(week_start))
    return await db.query_raw(
        """
        SELECT c."id", v."name" || ' / ' || c."name" AS court,
               ROUND(COALESCE(SUM(EXTRACT(EPOCH FROM (s."endsAt" - s."startsAt")) / 3600), 0)::numeric, 1)::float8 AS booked_hours,
               ROUND(100 * COALESCE(SUM(EXTRACT(EPOCH FROM (s."endsAt" - s."startsAt")) / 3600), 0)::numeric / 42, 1)::float8 AS prime_utilization_pct
        FROM "Court" c JOIN "Venue" v ON v."id" = c."venueId"
        LEFT JOIN "TrainingSession" s ON s."courtId" = c."id" AND s."status" <> 'CANCELLED'
             AND s."startsAt" >= $1::timestamp AND s."startsAt" < $1::timestamp + interval '7 days'
        WHERE c."isActive"
        GROUP BY c."id", v."name", c."name" ORDER BY booked_hours DESC
        """,
        lo.isoformat(),
    )


# ── Takım ──
@router.get("/teams")
async def teams(_: Staff, season_id: Annotated[str | None, Query(alias="seasonId")] = None):
    where: dict = {"isActive": True}
    if season_id:
        where["seasonId"] = season_id
    return await db.team.find_many(
        where=where, include={"headCoach": True, "feePlan": True}, order=[{"ageGroup": "asc"}, {"name": "asc"}]
    )


@router.post("/teams", status_code=status.HTTP_201_CREATED)
async def create_team(body: TeamIn, _: Management):
    return await db.team.create(data=body.model_dump(exclude_none=True))


@router.get("/teams/{team_id}/roster")
async def roster(team_id: str, _: Staff):
    return await db.teammembership.find_many(
        where={"teamId": team_id, "leftOn": None}, include={"athlete": True}, order={"jerseyNo": "asc"}
    )


# ── Haftalık şablon & program ──
@router.post("/slots", status_code=status.HTTP_201_CREATED)
async def create_slot(body: SlotIn, _: Management):
    data = body.model_dump(exclude_none=True)
    data["validFrom"] = as_dt(body.validFrom)
    if body.validTo:
        data["validTo"] = as_dt(body.validTo)
    return await db.recurringslot.create(data=data)


@router.post("/plans/generate", response_model=GenerateWeekOut)
async def generate_week(body: GenerateWeek, user: Coaching):
    """Şablondan haftalık programı üretir. Çakışma varsa 409 ve çakışma listesi döner."""
    try:
        r = await svc.generate_week(monday_of(body.weekStart), body.teamIds, user.staff_id, body.dryRun)
    except UniqueViolationError as e:
        raise HTTPException(409, f"Eşzamanlı üretim çakışması: {e}")
    except Exception as e:
        if _is_overlap_error(e):
            raise HTTPException(409, "Saha veya koç çakışması (veritabanı kısıtı)")
        raise
    out = GenerateWeekOut(
        weekStart=r.week_start,
        plans=r.plans,
        created=r.created,
        skippedExisting=r.skipped_existing,
        conflicts=[
            ConflictOut(
                kind=c.kind,
                teamId=c.draft.team_id,
                courtId=c.draft.court_id,
                coachId=c.draft.coach_id,
                startsAt=c.draft.starts_at,
                endsAt=c.draft.ends_at,
                otherRef=c.other_ref,
            )
            for c in r.conflicts
        ],
    )
    if r.conflicts and not body.dryRun:
        raise HTTPException(409, detail=out.model_dump(mode="json"))
    return out


@router.get("/plans/{team_id}")
async def team_week(team_id: str, _: Staff, week_start: Annotated[date, Query(alias="weekStart")]):
    ws = monday_of(week_start)
    return await db.trainingplan.find_unique(
        where={"teamId_weekStart": {"teamId": team_id, "weekStart": as_dt(ws)}},
        include={
            "sessions": {
                "include": {"drills": {"order_by": {"order": "asc"}}, "court": True, "coach": True},
                "order_by": {"startsAt": "asc"},
            }
        },
    )


@router.post("/plans/{plan_id}/publish")
async def publish_plan(plan_id: str, _: Coaching):
    return await db.trainingplan.update(where={"id": plan_id}, data={"status": "PUBLISHED", "publishedAt": utcnow()})


# ── Seans ──
@router.get("/sessions")
async def sessions(
    _: Staff,
    date_from: Annotated[date, Query(alias="from")],
    date_to: Annotated[date, Query(alias="to")],
    team_id: Annotated[str | None, Query(alias="teamId")] = None,
    court_id: Annotated[str | None, Query(alias="courtId")] = None,
    coach_id: Annotated[str | None, Query(alias="coachId")] = None,
):
    if (date_to - date_from).days > 62:
        raise HTTPException(422, "En fazla 62 günlük aralık")
    where: dict = {"startsAt": {"gte": as_dt(date_from), "lt": as_dt(date_to + timedelta(days=1))}}
    for k, v in (("teamId", team_id), ("courtId", court_id), ("coachId", coach_id)):
        if v:
            where[k] = v
    return await db.trainingsession.find_many(
        where=where, include={"team": True, "court": True, "coach": True}, order={"startsAt": "asc"}
    )


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: str, body: SessionPatch, _: Coaching):
    try:
        return await db.trainingsession.update(where={"id": session_id}, data=body.model_dump(exclude_none=True))
    except Exception as e:
        if _is_overlap_error(e):
            raise HTTPException(409, "Bu saatte saha veya koç dolu")
        raise


@router.put("/sessions/{session_id}/drills")
async def set_drills(session_id: str, drills: list[DrillIn], _: Coaching):
    async with db.tx() as tx:
        await tx.sessiondrill.delete_many(where={"sessionId": session_id})
        if drills:
            await tx.sessiondrill.create_many(
                data=[{"sessionId": session_id, **d.model_dump(exclude_none=True)} for d in drills]
            )
    return {"count": len(drills), "totalMinutes": sum(d.durationMin for d in drills)}


@router.put("/sessions/{session_id}/attendance")
async def attendance(session_id: str, body: AttendanceBulk, _: Coaching):
    n = await svc.record_attendance(session_id, [m.model_dump() for m in body.marks])
    return {"marked": n}


@router.post("/sessions/{session_id}/complete")
async def complete(session_id: str, _: Coaching):
    """Seansı kapatır → koç puantajına otomatik yazılır."""
    try:
        return await svc.complete_session(session_id)
    except ValueError as e:
        raise HTTPException(404, str(e))
