"""Ölçüm bataryaları, maç istatistikleri ve aylık veli raporları."""
from datetime import date, datetime

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..core.db import get_conn, rows
from ..core.security import SPORT_ROLES, CurrentUser, Role, assert_athlete_access, require
from ..services import reports
from ..services.notify import enqueue

router = APIRouter(prefix="/performance", tags=["performance"])


class MeasurementIn(BaseModel):
    code: str
    value: float


class AssessmentIn(BaseModel):
    athlete_id: int
    assessed_at: date
    context: str | None = None
    coach_note: str | None = None
    measurements: list[MeasurementIn]


class GameIn(BaseModel):
    team_id: int
    opponent: str
    played_at: datetime
    is_home: bool
    competition: str | None = None
    score_for: int | None = None
    score_against: int | None = None


class StatLine(BaseModel):
    athlete_id: int
    minutes: int = 0
    pts: int = 0
    fgm: int = 0
    fga: int = 0
    tpm: int = 0
    tpa: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = Field(0, le=5)


@router.get("/metrics")
async def metric_catalog(_: CurrentUser = Depends(require(*SPORT_ROLES)), conn: asyncpg.Connection = Depends(get_conn)):
    return rows(await conn.fetch("SELECT * FROM metric_definitions ORDER BY category, code"))


@router.post("/assessments", status_code=201)
async def create_assessment(data: AssessmentIn, user: CurrentUser = Depends(require(*SPORT_ROLES)),
                            conn: asyncpg.Connection = Depends(get_conn)):
    """Bir test gününün tüm ölçümleri tek istekte. Bilinmeyen metrik kodu → 422."""
    await assert_athlete_access(conn, user, data.athlete_id)
    codes = {m.code for m in data.measurements}
    ids = {r["code"]: r["id"] for r in await conn.fetch(
        "SELECT id, code FROM metric_definitions WHERE code = ANY($1::text[])", list(codes))}
    if missing := codes - ids.keys():
        raise HTTPException(422, f"Tanımsız metrik: {', '.join(sorted(missing))}")
    async with conn.transaction():
        aid = await conn.fetchval(
            """INSERT INTO assessments (athlete_id, assessor_id, assessed_at, context, coach_note)
               VALUES ($1,$2,$3,$4,$5) RETURNING id""",
            data.athlete_id, user.staff_id, data.assessed_at, data.context, data.coach_note)
        await conn.executemany(
            """INSERT INTO measurements (assessment_id, metric_id, value) VALUES ($1,$2,$3)
               ON CONFLICT (assessment_id, metric_id) DO UPDATE SET value = EXCLUDED.value""",
            [(aid, ids[m.code], m.value) for m in data.measurements])
    return {"id": aid}


@router.get("/teams/{team_id}/leaderboard/{code}")
async def leaderboard(team_id: int, code: str, _: CurrentUser = Depends(require(*SPORT_ROLES)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    """Takım içi sıralama (son ölçüm). Yön metrik tanımından gelir (sprint: düşük iyi)."""
    hib = await conn.fetchval("SELECT higher_is_better FROM metric_definitions WHERE code=$1", code)
    if hib is None:
        raise HTTPException(404, "Metrik yok")
    order = "DESC" if hib else "ASC"
    return rows(await conn.fetch(
        f"""SELECT * FROM (
              SELECT DISTINCT ON (a.id) a.id, a.first_name, a.last_name, m.value::float8 AS value, asm.assessed_at
              FROM team_memberships tm JOIN athletes a ON a.id = tm.athlete_id
              JOIN assessments asm ON asm.athlete_id = a.id
              JOIN measurements m ON m.assessment_id = asm.id
              JOIN metric_definitions d ON d.id = m.metric_id AND d.code = $2
              WHERE tm.team_id = $1 AND tm.end_date IS NULL
              ORDER BY a.id, asm.assessed_at DESC) x
            ORDER BY value {order}""", team_id, code))


@router.post("/games", status_code=201)
async def create_game(data: GameIn, _: CurrentUser = Depends(require(*SPORT_ROLES)),
                      conn: asyncpg.Connection = Depends(get_conn)):
    return {"id": await conn.fetchval(
        """INSERT INTO games (team_id, opponent, played_at, is_home, competition, score_for, score_against)
           VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id""", *data.model_dump().values())}


@router.put("/games/{game_id}/stats")
async def put_stats(game_id: int, lines: list[StatLine], _: CurrentUser = Depends(require(*SPORT_ROLES)),
                    conn: asyncpg.Connection = Depends(get_conn)):
    """Kutu skor (upsert). Tutarlılık: pts = 2·(FGM−3PM) + 3·3PM + FTM olmalı."""
    bad = [ln.athlete_id for ln in lines
           if ln.pts != 2 * (ln.fgm - ln.tpm) + 3 * ln.tpm + ln.ftm or ln.fgm > ln.fga or ln.tpm > ln.tpa
           or ln.ftm > ln.fta or ln.tpm > ln.fgm]
    if bad:
        raise HTTPException(422, f"Tutarsız istatistik (sporcu id): {bad}")
    cols = list(StatLine.model_fields)
    await conn.executemany(
        f"""INSERT INTO game_stats (game_id, {", ".join(cols)}) VALUES ($1, {", ".join(f"${i + 2}" for i in range(len(cols)))})
            ON CONFLICT (game_id, athlete_id) DO UPDATE SET {", ".join(f"{c}=EXCLUDED.{c}" for c in cols[1:])}""",
        [(game_id, *ln.model_dump().values()) for ln in lines])
    return {"lines": len(lines)}


@router.post("/reports/{period}/generate")
async def generate_reports(period: date, team_id: int | None = None,
                           _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                           conn: asyncpg.Connection = Depends(get_conn)):
    """Aylık raporları (taslak) üretir. Yayımlanmış raporlar korunur."""
    ids = [r["athlete_id"] for r in await conn.fetch(
        """SELECT athlete_id FROM v_athlete_current_team ct JOIN athletes a ON a.id = ct.athlete_id
           WHERE a.status = 'ACTIVE' AND ($1::int IS NULL OR ct.team_id = $1)""", team_id)]
    for aid in ids:
        await reports.build_monthly_report(conn, aid, period)
    return {"generated": len(ids)}


@router.patch("/reports/{report_id}")
async def annotate(report_id: int, coach_note: str, user: CurrentUser = Depends(require(*SPORT_ROLES)),
                   conn: asyncpg.Connection = Depends(get_conn)):
    athlete_id = await conn.fetchval("SELECT athlete_id FROM performance_reports WHERE id=$1", report_id)
    if athlete_id is None:
        raise HTTPException(404, "Rapor yok")
    await assert_athlete_access(conn, user, athlete_id)
    await conn.execute("UPDATE performance_reports SET coach_note=$2 WHERE id=$1 AND published_at IS NULL",
                       report_id, coach_note)
    return {"ok": True}


@router.post("/reports/{period}/publish")
async def publish(period: date, _: CurrentUser = Depends(require(Role.ADMIN, Role.MANAGER)),
                  conn: asyncpg.Connection = Depends(get_conn)):
    """Raporları dondurur ve velilere bildirim kuyruğuna ekler."""
    async with conn.transaction():
        recs = await conn.fetch(
            """UPDATE performance_reports SET published_at = now()
               WHERE period=$1 AND published_at IS NULL RETURNING id, athlete_id""", period.replace(day=1))
        for r in recs:
            for g in await conn.fetch(
                    """SELECT g.phone FROM athlete_guardians ag JOIN guardians g ON g.id = ag.guardian_id
                       WHERE ag.athlete_id=$1""", r["athlete_id"]):
                await enqueue(conn, "WHATSAPP", g["phone"], "monthly_report_ready",
                              {"report_id": r["id"]}, f"report:{r['id']}:{g['phone']}")
    return {"published": len(recs)}
