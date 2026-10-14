"""Haftalık dinamik antrenman programı, seans yönetimi ve yoklama."""
from datetime import date, datetime, timedelta

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.config import get_settings
from ..core.db import get_conn, rows
from ..core.security import SPORT_ROLES, STAFF_ROLES, CurrentUser, Role, require
from ..services import scheduling
from ..services.analytics import weekly_load

router = APIRouter(prefix="/training", tags=["training"])


class PlanIn(BaseModel):
    team_id: int
    coach_id: int
    facility_id: int
    weekday: int = Field(ge=1, le=7)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    duration_min: int = Field(ge=15, le=240)
    valid_from: date
    valid_to: date | None = None
    focus: str | None = None


class SessionIn(BaseModel):
    team_id: int | None = None
    coach_id: int
    facility_id: int
    type: str = Field("TEAM", pattern="^(TEAM|INDIVIDUAL|STRENGTH_CONDITIONING|GAME|TRIAL)$")
    starts_at: datetime
    ends_at: datetime
    focus: str | None = None
    planned_rpe: int | None = Field(None, ge=1, le=10)


class SessionPatch(BaseModel):
    coach_id: int | None = None
    facility_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    focus: str | None = None
    planned_rpe: int | None = Field(None, ge=1, le=10)
    notes: str | None = None
    status: str | None = Field(None, pattern="^(PLANNED|CANCELLED)$")
    cancel_reason: str | None = None


class BlockIn(BaseModel):
    drill_id: int | None = None
    duration_min: int = Field(ge=1, le=120)
    notes: str | None = None


class AttendanceIn(BaseModel):
    athlete_id: int
    status: str = Field(pattern="^(PRESENT|LATE|EXCUSED|ABSENT|INJURED)$")
    rpe: int | None = Field(None, ge=0, le=10)
    minutes: int | None = None


async def _coach_owns(conn: asyncpg.Connection, user: CurrentUser, session_id: int) -> None:
    if user.role != Role.COACH:
        return
    if await conn.fetchval("SELECT coach_id FROM training_sessions WHERE id=$1", session_id) != user.staff_id:
        raise HTTPException(403, "Bu seans size ait değil")


@router.get("/plans")
async def list_plans(team_id: int | None = None, _: CurrentUser = Depends(require(*STAFF_ROLES)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT p.*, t.name AS team_name, f.name AS facility_name FROM training_plans p
           JOIN teams t ON t.id=p.team_id JOIN facilities f ON f.id=p.facility_id
           WHERE ($1::int IS NULL OR p.team_id=$1) AND (p.valid_to IS NULL OR p.valid_to >= CURRENT_DATE)
           ORDER BY p.weekday, p.start_time""", team_id))


@router.post("/plans", status_code=201)
async def create_plan(data: PlanIn, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO training_plans (team_id, coach_id, facility_id, weekday, start_time, duration_min,
               valid_from, valid_to, focus) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id""",
        *data.model_dump().values())}


@router.post("/weeks/{monday}/generate")
async def generate_week(monday: date, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Şablonlardan haftayı üretir. Çakışmalar hata değil rapor olarak döner."""
    return await scheduling.generate_week(conn, monday)


@router.get("/sessions")
async def week_view(week: date | None = None, team_id: int | None = None, coach_id: int | None = None,
                    facility_id: int | None = None, user: CurrentUser = Depends(require(*STAFF_ROLES)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Takvim görünümü. Koç rolü filtre vermese de yalnız kendi seanslarını görür."""
    monday = scheduling.week_start(week or date.today())
    tz = get_settings().tz
    start = datetime.combine(monday, datetime.min.time(), tzinfo=tz)
    if user.role == Role.COACH:
        coach_id = user.staff_id
    return rows(await conn.fetch(
        """SELECT s.id, s.type, s.status, s.starts_at, s.ends_at, s.focus, s.planned_rpe,
                  s.team_id, t.name AS team_name, s.coach_id, st.first_name || ' ' || st.last_name AS coach,
                  s.facility_id, f.name AS facility,
                  (SELECT COUNT(*) FROM attendances a WHERE a.session_id=s.id AND a.status IN ('PRESENT','LATE')) AS present
           FROM training_sessions s
           LEFT JOIN teams t ON t.id=s.team_id JOIN staff st ON st.id=s.coach_id JOIN facilities f ON f.id=s.facility_id
           WHERE s.starts_at >= $1 AND s.starts_at < $2
             AND ($3::int IS NULL OR s.team_id=$3) AND ($4::int IS NULL OR s.coach_id=$4)
             AND ($5::int IS NULL OR s.facility_id=$5)
           ORDER BY s.starts_at""",
        start, start + timedelta(days=7), team_id, coach_id, facility_id))


@router.post("/sessions", status_code=201)
async def create_session(data: SessionIn, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """Tek seferlik seans (ek antrenman, maç, deneme). Çakışma → 409 (DB exclusion constraint)."""
    return {"id": await conn.fetchval(
        """INSERT INTO training_sessions (team_id, coach_id, facility_id, type, starts_at, ends_at, focus, planned_rpe)
           VALUES ($1,$2,$3,$4,$5,$6,$7,$8) RETURNING id""", *data.model_dump().values())}


@router.patch("/sessions/{session_id}")
async def patch_session(session_id: int, data: SessionPatch, user: CurrentUser = Depends(require(*SPORT_ROLES)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Haftalık programda tek seansı taşı / iptal et / içeriğini değiştir — şablon etkilenmez."""
    await _coach_owns(conn, user, session_id)
    fields = data.model_dump(exclude_unset=True)
    if user.role == Role.COACH:
        # Koç içerik düzenler; saha/koç/saat değişikliği yönetimde.
        fields = {k: v for k, v in fields.items() if k in ("focus", "planned_rpe", "notes")}
    if not fields:
        return {"updated": False}
    sets = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(fields))
    ok = await conn.fetchval(f"UPDATE training_sessions SET {sets} WHERE id=$1 AND status <> 'COMPLETED' RETURNING id",
                             session_id, *fields.values())
    if not ok:
        raise HTTPException(409, "Tamamlanmış seans değiştirilemez")
    return {"updated": True}


@router.put("/sessions/{session_id}/blocks")
async def set_blocks(session_id: int, blocks: list[BlockIn], user: CurrentUser = Depends(require(*SPORT_ROLES)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """Seans içeriği (drill sırası). Tamamı değiştirilir — sıralama çakışması olmaz."""
    await _coach_owns(conn, user, session_id)
    async with conn.transaction():
        await conn.execute("DELETE FROM session_blocks WHERE session_id=$1", session_id)
        await conn.executemany(
            "INSERT INTO session_blocks (session_id, drill_id, \"order\", duration_min, notes) VALUES ($1,$2,$3,$4,$5)",
            [(session_id, b.drill_id, i + 1, b.duration_min, b.notes) for i, b in enumerate(blocks)])
    return {"blocks": len(blocks), "total_minutes": sum(b.duration_min for b in blocks)}


@router.get("/sessions/{session_id}/attendance")
async def get_attendance(session_id: int, user: CurrentUser = Depends(require(*SPORT_ROLES)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    """Yoklama listesi: takım kadrosu + varsa kayıtlı durum (ön-doldurulmuş form)."""
    await _coach_owns(conn, user, session_id)
    return rows(await conn.fetch(
        """SELECT a.id AS athlete_id, a.first_name, a.last_name, at.status, at.rpe, at.minutes
           FROM training_sessions s
           JOIN team_memberships m ON m.team_id = s.team_id AND m.end_date IS NULL
           JOIN athletes a ON a.id = m.athlete_id
           LEFT JOIN attendances at ON at.session_id = s.id AND at.athlete_id = a.id
           WHERE s.id=$1 ORDER BY a.last_name""", session_id))


@router.put("/sessions/{session_id}/attendance")
async def take_attendance(session_id: int, items: list[AttendanceIn], complete: bool = True,
                          user: CurrentUser = Depends(require(*SPORT_ROLES)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    """Toplu yoklama (upsert) + seansı tamamla → koç puantajı otomatik oluşur."""
    await _coach_owns(conn, user, session_id)
    async with conn.transaction():
        await conn.executemany(
            """INSERT INTO attendances (session_id, athlete_id, status, rpe, minutes) VALUES ($1,$2,$3,$4,$5)
               ON CONFLICT (session_id, athlete_id) DO UPDATE
               SET status=EXCLUDED.status, rpe=EXCLUDED.rpe, minutes=EXCLUDED.minutes, recorded_at=now()""",
            [(session_id, i.athlete_id, i.status, i.rpe, i.minutes) for i in items])
        result = {"recorded": len(items)}
        if complete:
            result |= await scheduling.complete_session(conn, session_id)
    return result


@router.get("/drills")
async def drills(category: str | None = None, _: CurrentUser = Depends(require(*SPORT_ROLES)),
                 conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        "SELECT * FROM drills WHERE ($1::text IS NULL OR category=$1) ORDER BY category, name", category))


@router.get("/teams/{team_id}/load")
async def team_load(team_id: int, weeks: int = 6, _: CurrentUser = Depends(require(*SPORT_ROLES)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Takımın haftalık sRPE yükü, monotoni ve strain (Foster 1998).
    Monotoni > 2.0 → haftalık plan çok tekdüze, yoğun/hafif gün dalgalanması eklenmeli."""
    tz = get_settings().timezone
    recs = await conn.fetch(
        """SELECT date_trunc('week', s.starts_at AT TIME ZONE $3)::date AS week,
                  EXTRACT(ISODOW FROM s.starts_at AT TIME ZONE $3)::int AS dow,
                  AVG(a.rpe * COALESCE(a.minutes, EXTRACT(EPOCH FROM s.ends_at - s.starts_at)::int / 60))::float8 AS load
           FROM training_sessions s JOIN attendances a ON a.session_id = s.id
           WHERE s.team_id=$1 AND s.status='COMPLETED' AND a.rpe IS NOT NULL
             AND a.status IN ('PRESENT','LATE') AND s.starts_at >= now() - make_interval(weeks => $2)
           GROUP BY 1, 2 ORDER BY 1, 2""", team_id, weeks, tz)
    by_week: dict[date, list[int]] = {}
    for r in recs:
        by_week.setdefault(r["week"], [0] * 7)[r["dow"] - 1] += int(r["load"])
    return [{"week": w, **weekly_load(d).__dict__} for w, d in sorted(by_week.items())]
