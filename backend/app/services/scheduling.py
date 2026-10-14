"""Haftalık dinamik antrenman programı ve puantaj.

Akış: TrainingPlan (şablon) ─generate_week→ TrainingSession (somut)
      ─koç yoklama alır / complete→ TimeEntry (puantaj) ─close_month→ Timesheet ─→ Payroll
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import asyncpg

from ..core.config import get_settings


@dataclass(frozen=True)
class Occurrence:
    plan_id: int
    team_id: int
    coach_id: int
    facility_id: int
    starts_at: datetime
    ends_at: datetime
    focus: str | None


def week_start(d: date) -> date:
    return d - timedelta(days=d.isoweekday() - 1)


def plan_occurrences(plans: list[dict], monday: date, tz: ZoneInfo) -> list[Occurrence]:
    """Şablonlardan o haftanın seanslarını üretir (saf fonksiyon).

    Saatler yerel (Europe/Istanbul) tanımlanır, UTC'ye çevrilerek saklanır.
    """
    out: list[Occurrence] = []
    for p in plans:
        day = monday + timedelta(days=p["weekday"] - 1)
        if day < p["valid_from"] or (p["valid_to"] and day > p["valid_to"]):
            continue
        hh, mm = map(int, p["start_time"].split(":"))
        start = datetime.combine(day, time(hh, mm), tzinfo=tz)
        out.append(Occurrence(p["id"], p["team_id"], p["coach_id"], p["facility_id"], start,
                              start + timedelta(minutes=p["duration_min"]), p["focus"]))
    return out


async def generate_week(conn: asyncpg.Connection, monday: date) -> dict:
    """Haftanın seanslarını şablonlardan oluşturur. Idempotent; çakışanları raporlar, durmaz."""
    monday = week_start(monday)
    plans = await conn.fetch(
        """SELECT id, team_id, coach_id, facility_id, weekday, start_time, duration_min,
                  valid_from, valid_to, focus FROM training_plans
           WHERE valid_from <= $2 AND (valid_to IS NULL OR valid_to >= $1)""",
        monday, monday + timedelta(days=6))
    created, skipped, conflicts = 0, 0, []
    for occ in plan_occurrences([dict(p) for p in plans], monday, get_settings().tz):
        try:
            # Savepoint: tek seansın çakışması tüm haftayı geri almasın.
            async with conn.transaction():
                sid = await conn.fetchval(
                    """INSERT INTO training_sessions (plan_id, team_id, coach_id, facility_id, type,
                           starts_at, ends_at, focus)
                       VALUES ($1,$2,$3,$4,'TEAM',$5,$6,$7)
                       ON CONFLICT (plan_id, starts_at) DO NOTHING RETURNING id""",
                    occ.plan_id, occ.team_id, occ.coach_id, occ.facility_id,
                    occ.starts_at, occ.ends_at, occ.focus)
            if sid:
                created += 1
            else:
                skipped += 1
        except asyncpg.ExclusionViolationError as exc:
            conflicts.append({"plan_id": occ.plan_id, "starts_at": occ.starts_at.isoformat(),
                              "reason": exc.constraint_name})
    return {"week": monday.isoformat(), "created": created, "already_existed": skipped,
            "conflicts": conflicts}


async def complete_session(conn: asyncpg.Connection, session_id: int, approved_by: int | None = None) -> dict:
    """Seansı tamamlar ve koçun puantajına otomatik satır yazar (seans başına tek satır)."""
    async with conn.transaction():
        s = await conn.fetchrow(
            """UPDATE training_sessions SET status='COMPLETED'
               WHERE id=$1 AND status <> 'CANCELLED' RETURNING id, coach_id, starts_at, ends_at""",
            session_id)
        if s is None:
            raise ValueError("Seans bulunamadı ya da iptal edilmiş")
        minutes = int((s["ends_at"] - s["starts_at"]).total_seconds() // 60)
        await conn.execute(
            """INSERT INTO time_entries (staff_id, session_id, clock_in, clock_out, minutes, source,
                   approved_by_id, approved_at)
               VALUES ($1,$2,$3,$4,$5,'SESSION_AUTO',$6, CASE WHEN $6::int IS NULL THEN NULL ELSE now() END)
               ON CONFLICT (session_id) DO NOTHING""",
            s["coach_id"], session_id, s["starts_at"], s["ends_at"], minutes, approved_by)
    return {"session_id": session_id, "minutes": minutes}


async def close_month(conn: asyncpg.Connection, period: date) -> list[dict]:
    """Ay sonu puantajı: time_entries → timesheets (DRAFT). LOCKED olanlara dokunmaz."""
    period = period.replace(day=1)
    nxt = (period + timedelta(days=32)).replace(day=1)
    tz = get_settings().timezone
    async with conn.transaction():
        recs = await conn.fetch(
            """WITH agg AS (
                 SELECT staff_id, SUM(minutes)::int AS total, COUNT(session_id)::int AS sessions
                 FROM time_entries
                 WHERE (clock_in AT TIME ZONE $3)::date >= $1 AND (clock_in AT TIME ZONE $3)::date < $2
                 GROUP BY staff_id)
               INSERT INTO timesheets (staff_id, period, total_minutes, session_count)
               SELECT staff_id, $1, total, sessions FROM agg
               ON CONFLICT (staff_id, period) DO UPDATE
                 SET total_minutes = EXCLUDED.total_minutes, session_count = EXCLUDED.session_count
                 WHERE timesheets.status <> 'LOCKED'
               RETURNING id, staff_id, total_minutes, session_count, status""",
            period, nxt, tz)
        await conn.execute(
            """UPDATE time_entries te SET timesheet_id = ts.id FROM timesheets ts
               WHERE ts.staff_id = te.staff_id AND ts.period = $1 AND ts.status <> 'LOCKED'
                 AND (te.clock_in AT TIME ZONE $3)::date >= $1 AND (te.clock_in AT TIME ZONE $3)::date < $2""",
            period, nxt, tz)
    return [dict(r) for r in recs]


async def draft_payrolls(conn: asyncpg.Connection, period: date, employer_cost_factor: float = 1.2075) -> int:
    """Puantajdan brüt bordro taslağı. employer_cost_factor: SGK işveren payı (%20.75, 5 puan
    teşvik öncesi) için yaklaşık katsayı — kesin net/vergi mali müşavirin bordrosundan girilir."""
    period = period.replace(day=1)
    async with conn.transaction():
        n = await conn.fetchval(
            """WITH src AS (
                 SELECT s.id AS staff_id, ts.id AS timesheet_id,
                        COALESCE(s.monthly_salary, 0) AS base,
                        ROUND(COALESCE(s.hourly_rate, 0) * COALESCE(ts.total_minutes, 0) / 60.0, 2) AS hourly
                 FROM staff s
                 LEFT JOIN timesheets ts ON ts.staff_id = s.id AND ts.period = $1
                 WHERE s.hire_date <= ($1::date + interval '1 month' - interval '1 day')
                   AND (s.terminated_at IS NULL OR s.terminated_at >= $1)
                   AND (s.monthly_salary IS NOT NULL OR ts.id IS NOT NULL)),
               ins AS (
                 INSERT INTO payrolls (staff_id, period, timesheet_id, base_gross, hourly_gross, employer_cost)
                 SELECT staff_id, $1, timesheet_id, base, hourly, ROUND((base + hourly) * $2::numeric, 2) FROM src
                 ON CONFLICT (staff_id, period) DO UPDATE
                   SET base_gross = EXCLUDED.base_gross, hourly_gross = EXCLUDED.hourly_gross,
                       employer_cost = EXCLUDED.employer_cost, timesheet_id = EXCLUDED.timesheet_id
                   WHERE payrolls.status = 'DRAFT'
                 RETURNING 1)
               SELECT COUNT(*) FROM ins""",
            period, employer_cost_factor)
        await conn.execute(
            "UPDATE timesheets SET status='APPROVED' WHERE period=$1 AND status='DRAFT'", period)
    return n
