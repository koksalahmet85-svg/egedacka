"""Haftalık program üretimi, yoklama ve puantaj otomasyonu."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from ..core.db import db
from ..core.timeutil import as_date, as_dt, utcnow
from ..domain.scheduling import Booked, Conflict, Slot, expand_week, find_conflicts


@dataclass
class WeekGeneration:
    week_start: date
    plans: int = 0
    created: int = 0
    skipped_existing: int = 0
    conflicts: list[Conflict] = field(default_factory=list)


async def generate_week(
    week_start: date, team_ids: list[str] | None, created_by: str | None, dry_run: bool
) -> WeekGeneration:
    """Şablon slotlardan haftanın seanslarını üretir.

    Çakışma varsa hiçbir şey yazılmaz (hepsi ya da hiçbiri) ve çakışmalar döner.
    Var olan seanslar (aynı takım + başlangıç) tekrar üretilmez → idempotent.
    """
    res = WeekGeneration(week_start=week_start)
    week_end = week_start + timedelta(days=7)
    where: dict = {
        "validFrom": {"lt": as_dt(week_end)},
        "OR": [{"validTo": None}, {"validTo": {"gte": as_dt(week_start)}}],
    }
    if team_ids:
        where["teamId"] = {"in": team_ids}
    rows = await db.recurringslot.find_many(where=where)
    slots = [
        Slot(
            r.id,
            r.teamId,
            r.courtId,
            r.coachId,
            r.weekday,
            r.startTime,
            r.endTime,
            as_date(r.validFrom),
            as_date(r.validTo) if r.validTo else None,
        )
        for r in rows
    ]
    drafts = expand_week(slots, week_start)
    if not drafts:
        return res

    lo, hi = min(d.starts_at for d in drafts), max(d.ends_at for d in drafts)
    existing = await db.trainingsession.find_many(
        where={"status": {"not": "CANCELLED"}, "startsAt": {"lt": hi}, "endsAt": {"gt": lo}}
    )
    already = {(s.teamId, s.startsAt) for s in existing}
    fresh = [d for d in drafts if (d.team_id, d.starts_at) not in already]
    res.skipped_existing = len(drafts) - len(fresh)

    res.conflicts = find_conflicts(fresh, [Booked(s.id, s.courtId, s.coachId, s.startsAt, s.endsAt) for s in existing])
    if res.conflicts or dry_run or not fresh:
        return res

    async with db.tx() as tx:
        plan_ids: dict[str, str] = {}
        for team_id in {d.team_id for d in fresh}:
            data: dict = {"teamId": team_id, "weekStart": as_dt(week_start)}
            if created_by:
                data["createdById"] = created_by
            plan = await tx.trainingplan.upsert(
                where={"teamId_weekStart": {"teamId": team_id, "weekStart": as_dt(week_start)}},
                data={"create": data, "update": {}},
            )
            plan_ids[team_id] = plan.id
        res.plans = len(plan_ids)
        # DB'deki EXCLUDE kısıtı eşzamanlı yazımlarda son savunma hattıdır.
        res.created = await tx.trainingsession.create_many(
            data=[
                {
                    "teamId": d.team_id,
                    "planId": plan_ids[d.team_id],
                    "courtId": d.court_id,
                    "coachId": d.coach_id,
                    "startsAt": d.starts_at,
                    "endsAt": d.ends_at,
                }
                for d in fresh
            ]
        )
    return res


async def record_attendance(session_id: str, marks: list[dict]) -> int:
    """Toplu yoklama (upsert). marks: [{athleteId, status, rpe?, minutes?, note?}]"""
    async with db.tx() as tx:
        for m in marks:
            payload = {k: m.get(k) for k in ("status", "rpe", "minutes", "note")}
            await tx.attendance.upsert(
                where={"sessionId_athleteId": {"sessionId": session_id, "athleteId": m["athleteId"]}},
                data={"create": {"sessionId": session_id, "athleteId": m["athleteId"], **payload}, "update": payload},
            )
    return len(marks)


async def complete_session(session_id: str) -> dict:
    """Seansı tamamlar ve koçun puantajına otomatik yazar (onay bekler)."""
    s = await db.trainingsession.update(where={"id": session_id}, data={"status": "COMPLETED"})
    if s is None:
        raise ValueError("seans bulunamadı")
    minutes = int((s.endsAt - s.startsAt).total_seconds() // 60)
    entry = await db.timeentry.upsert(
        where={"staffId_sessionId": {"staffId": s.coachId, "sessionId": s.id}},
        data={
            "create": {
                "staffId": s.coachId,
                "sessionId": s.id,
                "workDate": as_dt(s.startsAt.date()),
                "clockIn": s.startsAt,
                "clockOut": s.endsAt,
                "minutes": minutes,
                "source": "SESSION_AUTO",
            },
            "update": {},
        },
    )
    return {"sessionId": s.id, "timeEntryId": entry.id, "minutes": minutes}


async def clock(staff_id: str, action: str) -> dict:
    """QR / mobil giriş-çıkış."""
    now = utcnow()
    open_entry = await db.timeentry.find_first(
        where={"staffId": staff_id, "clockOut": None, "source": {"not": "SESSION_AUTO"}}, order={"clockIn": "desc"}
    )
    if action == "in":
        if open_entry:
            raise ValueError("açık giriş kaydı var, önce çıkış yapın")
        e = await db.timeentry.create(
            data={"staffId": staff_id, "workDate": as_dt(now.date()), "clockIn": now, "source": "QR_CHECKIN"}
        )
        return {"id": e.id, "clockIn": e.clockIn}
    if not open_entry:
        raise ValueError("açık giriş kaydı yok")
    minutes = int((now - open_entry.clockIn).total_seconds() // 60)
    e = await db.timeentry.update(where={"id": open_entry.id}, data={"clockOut": now, "minutes": minutes})
    assert e is not None
    return {"id": e.id, "minutes": minutes}
