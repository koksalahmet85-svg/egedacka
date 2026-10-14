"""Sezon, takım, saha kataloğu."""
import asyncpg
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ..core.db import get_conn, rows
from ..core.security import STAFF_ROLES, CurrentUser, Role, require

router = APIRouter(tags=["teams"])


class TeamIn(BaseModel):
    season_id: int
    name: str
    age_group: str
    level: str = Field(pattern="^(SCHOOL|DEVELOPMENT|PERFORMANCE)$")
    head_coach_id: int | None = None
    max_athletes: int = 15
    default_fee_plan_id: int | None = None


class FacilityIn(BaseModel):
    name: str
    type: str = Field(pattern="^(COURT|GYM|CONDITIONING|CLASSROOM)$")
    capacity: int
    hourly_cost: float = 0


@router.get("/teams")
async def list_teams(season_id: int | None = None, _: CurrentUser = Depends(require(*STAFF_ROLES)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    """Takımlar + doluluk. Kapasite aşımı satış ekibi için 'kontenjan dolu' sinyalidir."""
    return rows(await conn.fetch(
        """SELECT t.id, t.name, t.age_group, t.level, t.max_athletes, t.head_coach_id,
                  s.first_name || ' ' || s.last_name AS head_coach,
                  COUNT(m.id) FILTER (WHERE m.end_date IS NULL) AS roster_size
           FROM teams t
           JOIN seasons se ON se.id = t.season_id
           LEFT JOIN staff s ON s.id = t.head_coach_id
           LEFT JOIN team_memberships m ON m.team_id = t.id
           WHERE ($1::int IS NULL AND se.is_active) OR t.season_id = $1
           GROUP BY t.id, s.id ORDER BY t.name""", season_id))


@router.post("/teams", status_code=201)
async def create_team(data: TeamIn, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO teams (season_id, name, age_group, level, head_coach_id, max_athletes, default_fee_plan_id)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""", *data.model_dump().values())}


@router.get("/teams/{team_id}/roster")
async def roster(team_id: int, _: CurrentUser = Depends(require(*STAFF_ROLES)),
                 conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch(
        """SELECT a.id, a.first_name, a.last_name, a.birth_date, a.position, m.jersey, a.status
           FROM team_memberships m JOIN athletes a ON a.id = m.athlete_id
           WHERE m.team_id=$1 AND m.end_date IS NULL ORDER BY a.last_name""", team_id))


@router.post("/teams/{team_id}/coaches/{staff_id}", status_code=201)
async def add_assistant(team_id: int, staff_id: int, role: str = "ASSISTANT",
                        _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    await conn.execute(
        """INSERT INTO team_coaches (team_id, staff_id, role) VALUES ($1,$2,$3)
           ON CONFLICT (team_id, staff_id) DO UPDATE SET role = EXCLUDED.role""", team_id, staff_id, role)
    return {"ok": True}


@router.get("/facilities")
async def list_facilities(_: CurrentUser = Depends(require(*STAFF_ROLES)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch("SELECT * FROM facilities WHERE is_active ORDER BY name"))


@router.post("/facilities", status_code=201)
async def create_facility(data: FacilityIn, _: CurrentUser = Depends(require(Role.ADMIN)),
                          conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        "INSERT INTO facilities (name, type, capacity, hourly_cost) VALUES ($1,$2,$3,$4) RETURNING id",
        data.name, data.type, data.capacity, data.hourly_cost)}


@router.get("/facilities/utilization")
async def utilization(weeks: int = 4, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    """Saha doluluğu (07:00-23:00 penceresine göre). Düşük doluluk = kira optimizasyonu fırsatı."""
    return rows(await conn.fetch(
        """SELECT f.id, f.name,
                  COALESCE(SUM(EXTRACT(EPOCH FROM s.ends_at - s.starts_at)) / 3600, 0)::float8 AS booked_hours,
                  ($1 * 7 * 16)::float8 AS available_hours,
                  COALESCE(SUM(EXTRACT(EPOCH FROM s.ends_at - s.starts_at)) / 3600, 0)::float8 / ($1 * 7 * 16)
                    AS utilization
           FROM facilities f LEFT JOIN training_sessions s ON s.facility_id = f.id
             AND s.status <> 'CANCELLED' AND s.starts_at >= now() - make_interval(weeks => $1)
             AND s.starts_at < now()
           WHERE f.is_active GROUP BY f.id ORDER BY utilization""", weeks))
