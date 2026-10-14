"""Sporcu & veli yönetimi + gelişim analitiği."""
from datetime import date

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..core.db import get_conn, row, rows
from ..core.security import (FINANCE_ROLES, SPORT_ROLES, STAFF_ROLES, CurrentUser, Role,
                             assert_athlete_access, require)
from ..services import reports

router = APIRouter(prefix="/athletes", tags=["athletes"])


class GuardianIn(BaseModel):
    full_name: str
    phone: str = Field(pattern=r"^\+90\d{10}$", examples=["+905321234567"])
    email: str | None = None
    relation: str = "VELİ"
    kvkk_consent: bool = Field(description="Açık rıza alınmadan kayıt açılmaz")
    marketing_consent: bool = False


class AthleteIn(BaseModel):
    first_name: str
    last_name: str
    birth_date: date
    gender: str = Field(pattern="^(MALE|FEMALE)$")
    position: str | None = None
    license_no: str | None = None
    health_report_expires_at: date | None = None
    photo_consent: bool = False
    team_id: int | None = None
    fee_plan_id: int | None = None
    discount_pct: float = 0
    guardian: GuardianIn


class AthletePatch(BaseModel):
    position: str | None = None
    license_no: str | None = None
    health_report_expires_at: date | None = None
    photo_consent: bool | None = None
    status: str | None = Field(None, pattern="^(TRIAL|ACTIVE|FROZEN|LEFT)$")
    left_reason: str | None = None


async def create_athlete_tx(conn: asyncpg.Connection, data: AthleteIn, lead_id: int | None = None) -> int:
    """Sporcu + veli + takım üyeliği + aidat aboneliği tek transaction'da.
    CRM'deki lead dönüşümü de bu fonksiyonu kullanır."""
    if not data.guardian.kvkk_consent:
        raise HTTPException(422, "KVKK açık rızası olmadan kayıt oluşturulamaz")
    async with conn.transaction():
        g = data.guardian
        guardian_id = await conn.fetchval(
            """INSERT INTO guardians (full_name, phone, email, kvkk_consent_at, marketing_consent_at)
               VALUES ($1,$2,$3, now(), CASE WHEN $4 THEN now() END)
               ON CONFLICT (phone) DO UPDATE SET email = COALESCE(EXCLUDED.email, guardians.email)
               RETURNING id""",
            g.full_name, g.phone, g.email, g.marketing_consent)
        athlete_id = await conn.fetchval(
            """INSERT INTO athletes (first_name, last_name, birth_date, gender, position, license_no,
                   health_report_expires_at, photo_consent, status)
               VALUES ($1,$2,$3,$4,$5,$6,$7,$8,'ACTIVE') RETURNING id""",
            data.first_name.strip().upper(), data.last_name.strip().upper(), data.birth_date, data.gender,
            data.position, data.license_no, data.health_report_expires_at, data.photo_consent)
        await conn.execute(
            """INSERT INTO athlete_guardians (athlete_id, guardian_id, relation, is_primary)
               VALUES ($1,$2,$3,true)""", athlete_id, guardian_id, g.relation)
        fee_plan_id = data.fee_plan_id
        if data.team_id:
            await conn.execute(
                "INSERT INTO team_memberships (athlete_id, team_id, start_date) VALUES ($1,$2,CURRENT_DATE)",
                athlete_id, data.team_id)
            fee_plan_id = fee_plan_id or await conn.fetchval(
                "SELECT default_fee_plan_id FROM teams WHERE id=$1", data.team_id)
        if fee_plan_id:
            await conn.execute(
                """INSERT INTO subscriptions (athlete_id, guardian_id, fee_plan_id, discount_pct, start_date)
                   VALUES ($1,$2,$3,$4,CURRENT_DATE)""",
                athlete_id, guardian_id, fee_plan_id, data.discount_pct)
        if lead_id:
            await conn.execute(
                "UPDATE leads SET athlete_id=$1, stage='WON', converted_at=now() WHERE id=$2",
                athlete_id, lead_id)
    return athlete_id


@router.get("")
async def list_athletes(
    team_id: int | None = None, status: str | None = None, q: str | None = None,
    limit: int = Query(50, le=200), offset: int = 0,
    user: CurrentUser = Depends(require(*STAFF_ROLES)), conn: asyncpg.Connection = Depends(get_conn),
):
    coach_only = user.staff_id if user.role == Role.COACH else None
    recs = await conn.fetch(
        """SELECT a.id, a.first_name, a.last_name, a.birth_date, a.gender, a.status, a.position,
                  a.health_report_expires_at, ct.team_id, ct.team_name, COUNT(*) OVER() AS total
           FROM athletes a LEFT JOIN v_athlete_current_team ct ON ct.athlete_id = a.id
           WHERE ($1::int IS NULL OR ct.team_id = $1)
             AND ($2::athlete_status IS NULL OR a.status = $2)
             AND ($3::text IS NULL OR (a.first_name || ' ' || a.last_name) ILIKE '%' || $3 || '%')
             AND ($6::int IS NULL OR ct.head_coach_id = $6 OR EXISTS (
                  SELECT 1 FROM team_coaches tc WHERE tc.team_id = ct.team_id AND tc.staff_id = $6))
           ORDER BY a.last_name, a.first_name LIMIT $4 OFFSET $5""",
        team_id, status, q, limit, offset, coach_only)
    return {"total": recs[0]["total"] if recs else 0, "items": [dict(r) for r in recs]}


@router.post("", status_code=201)
async def create_athlete(data: AthleteIn, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                         conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await create_athlete_tx(conn, data)}


@router.get("/{athlete_id}")
async def get_athlete(athlete_id: int, user: CurrentUser = Depends(require(*STAFF_ROLES, Role.GUARDIAN)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    await assert_athlete_access(conn, user, athlete_id)
    a = row(await conn.fetchrow(
        """SELECT a.*, ct.team_id, ct.team_name FROM athletes a
           LEFT JOIN v_athlete_current_team ct ON ct.athlete_id = a.id WHERE a.id=$1""", athlete_id))
    if not a:
        raise HTTPException(404, "Sporcu bulunamadı")
    a["guardians"] = rows(await conn.fetch(
        """SELECT g.id, g.full_name, g.phone, g.email, ag.relation, ag.is_primary FROM athlete_guardians ag
           JOIN guardians g ON g.id = ag.guardian_id WHERE ag.athlete_id=$1""", athlete_id))
    return a


@router.patch("/{athlete_id}")
async def patch_athlete(athlete_id: int, data: AthletePatch,
                        _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    fields = data.model_dump(exclude_unset=True)
    if not fields:
        return {"updated": False}
    async with conn.transaction():
        if fields.get("status") == "LEFT":
            fields["left_at"] = date.today()
            # Ayrılan sporcunun aboneliği ve takım üyeliği kapanır → sonraki ay fatura kesilmez.
            await conn.execute("UPDATE subscriptions SET end_date=CURRENT_DATE WHERE athlete_id=$1 AND end_date IS NULL",
                               athlete_id)
            await conn.execute("UPDATE team_memberships SET end_date=CURRENT_DATE WHERE athlete_id=$1 AND end_date IS NULL",
                               athlete_id)
        cols = list(fields)
        sets = ", ".join(f"{c} = ${i + 2}" for i, c in enumerate(cols))
        await conn.execute(f"UPDATE athletes SET {sets} WHERE id=$1", athlete_id, *fields.values())
    return {"updated": True}


@router.post("/{athlete_id}/transfer")
async def transfer_team(athlete_id: int, team_id: int,
                        _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    """Takım değişikliği: eski üyelik kapanır, geçmiş korunur."""
    async with conn.transaction():
        await conn.execute(
            "UPDATE team_memberships SET end_date=CURRENT_DATE WHERE athlete_id=$1 AND end_date IS NULL", athlete_id)
        await conn.execute(
            "INSERT INTO team_memberships (athlete_id, team_id, start_date) VALUES ($1,$2,CURRENT_DATE)",
            athlete_id, team_id)
    return {"athlete_id": athlete_id, "team_id": team_id}


@router.get("/{athlete_id}/progress")
async def progress(athlete_id: int, user: CurrentUser = Depends(require(*SPORT_ROLES, Role.GUARDIAN)),
                   conn: asyncpg.Connection = Depends(get_conn)):
    """Gelişim kartı: metrik değişimleri (SWC kararı), yaş grubu z-skoru, olgunlaşma, maç ortalamaları."""
    await assert_athlete_access(conn, user, athlete_id)
    return {
        "metrics": await reports.metric_progress(conn, athlete_id),
        "maturity": await reports.maturity(conn, athlete_id),
        "games": await reports.game_averages(conn, athlete_id),
    }


@router.get("/{athlete_id}/attendance-trend")
async def attendance(athlete_id: int, weeks: int = Query(12, le=52),
                     user: CurrentUser = Depends(require(*SPORT_ROLES, Role.GUARDIAN)),
                     conn: asyncpg.Connection = Depends(get_conn)):
    await assert_athlete_access(conn, user, athlete_id)
    return await reports.attendance_trend(conn, athlete_id, weeks)


@router.get("/{athlete_id}/metrics/{code}")
async def metric_series(athlete_id: int, code: str,
                        user: CurrentUser = Depends(require(*SPORT_ROLES, Role.GUARDIAN)),
                        conn: asyncpg.Connection = Depends(get_conn)):
    await assert_athlete_access(conn, user, athlete_id)
    return rows(await conn.fetch(
        """SELECT a.assessed_at, m.value::float8 AS value FROM measurements m
           JOIN assessments a ON a.id = m.assessment_id JOIN metric_definitions d ON d.id = m.metric_id
           WHERE a.athlete_id=$1 AND d.code=$2 ORDER BY a.assessed_at""", athlete_id, code))


@router.get("/{athlete_id}/balance")
async def balance(athlete_id: int, user: CurrentUser = Depends(require(*FINANCE_ROLES, Role.GUARDIAN)),
                  conn: asyncpg.Connection = Depends(get_conn)):
    await assert_athlete_access(conn, user, athlete_id)
    return rows(await conn.fetch(
        "SELECT * FROM v_invoice_balance WHERE athlete_id=$1 ORDER BY due_date DESC", athlete_id))
