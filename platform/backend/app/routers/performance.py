"""Fiziksel testler, maç istatistikleri, aylık raporlar."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status

from ..core.db import db
from ..core.deps import Coaching, User, assert_guardian_owns_athlete
from ..core.timeutil import as_dt, utcnow
from ..domain.performance import BoxScore, efg_pct, pir, ts_pct
from ..schemas.performance import BoxScoreIn, GameIn, ReportPublish, TestBatch
from ..services.reports import generate_monthly_reports

router = APIRouter(prefix="/performance", tags=["Performans"])


@router.get("/test-types")
async def test_types(_: User):
    return await db.physicaltesttype.find_many(order=[{"category": "asc"}, {"code": "asc"}])


@router.post("/tests", status_code=status.HTTP_201_CREATED)
async def record_tests(body: TestBatch, user: Coaching):
    """Toplu test girişi (ör. tüm U14'ün CMJ ölçümü tek istekte)."""
    codes = {r.testCode for r in body.results}
    types = {t.code: t.id for t in await db.physicaltesttype.find_many(where={"code": {"in": list(codes)}})}
    missing = codes - types.keys()
    if missing:
        raise HTTPException(422, f"Bilinmeyen test kodu: {', '.join(sorted(missing))}")
    rows = []
    for r in body.results:
        row = {
            "athleteId": r.athleteId,
            "testTypeId": types[r.testCode],
            "value": Decimal(str(r.value)),
            "attempt": r.attempt,
            "measuredAt": r.measuredAt,
            "sessionId": r.sessionId,
            "notes": r.notes,
        }
        if user.staff_id:
            row["measuredById"] = user.staff_id
        rows.append({k: v for k, v in row.items() if v is not None})
    return {"created": await db.physicaltestresult.create_many(data=rows)}


@router.get("/athletes/{athlete_id}/progress")
async def progress(athlete_id: str, user: User, code: str):
    """Tek test için zaman serisi + takım ortalaması (aynı yaş grubu kıyası)."""
    await assert_guardian_owns_athlete(user, athlete_id)
    return await db.query_raw(
        """
        WITH me AS (
          SELECT r."measuredAt"::date AS day, MAX(r."value")::float8 AS value
          FROM "PhysicalTestResult" r JOIN "PhysicalTestType" t ON t."id" = r."testTypeId"
          WHERE r."athleteId" = $1::uuid AND t."code" = $2
          GROUP BY 1
        ), team AS (
          SELECT tm2."athleteId" FROM "TeamMembership" tm
          JOIN "TeamMembership" tm2 ON tm2."teamId" = tm."teamId" AND tm2."leftOn" IS NULL
          WHERE tm."athleteId" = $1::uuid AND tm."leftOn" IS NULL
        )
        SELECT me.day, me.value,
               (SELECT AVG(r."value")::float8 FROM "PhysicalTestResult" r
                JOIN "PhysicalTestType" t ON t."id" = r."testTypeId"
                WHERE t."code" = $2 AND r."athleteId" IN (SELECT "athleteId" FROM team)
                  AND r."measuredAt"::date BETWEEN me.day - 14 AND me.day + 14) AS team_avg
        FROM me ORDER BY me.day
        """,
        athlete_id,
        code,
    )


@router.post("/games", status_code=status.HTTP_201_CREATED)
async def create_game(body: GameIn, _: Coaching):
    return await db.game.create(data=body.model_dump(exclude_none=True))


@router.put("/games/{game_id}/boxscore")
async def boxscore(game_id: str, rows: list[BoxScoreIn], _: Coaching):
    for r in rows:
        if r.fgm2 > r.fga2 or r.fgm3 > r.fga3 or r.ftm > r.fta:
            raise HTTPException(422, f"İsabet > deneme: {r.athleteId}")
        if r.points != 2 * r.fgm2 + 3 * r.fgm3 + r.ftm:
            raise HTTPException(422, f"Sayı tutarsız (2×İ2 + 3×İ3 + SA): {r.athleteId}")
    async with db.tx() as tx:
        await tx.gamestat.delete_many(where={"gameId": game_id})
        await tx.gamestat.create_many(data=[{"gameId": game_id, **r.model_dump(exclude_none=True)} for r in rows])
    out = []
    for r in rows:
        b = BoxScore(
            **r.model_dump(exclude={"athleteId", "plusMinus", "foulsDrawn", "blkAgainst"}),
            fouls_drawn=r.foulsDrawn,
            blocks_against=r.blkAgainst,
        )
        out.append(
            {"athleteId": r.athleteId, "pir": pir(b), "efgPct": efg_pct(b), "tsPct": ts_pct(b), "rebounds": b.rebounds}
        )
    return out


@router.post("/reports/generate")
async def gen_reports(period: date, _: Coaching):
    return {"generated": await generate_monthly_reports(period)}


@router.get("/reports")
async def list_reports(_: Coaching, period: date, team_id: str | None = None):
    where: dict = {"period": as_dt(period.replace(day=1))}
    if team_id:
        where["athlete"] = {"is": {"memberships": {"some": {"teamId": team_id, "leftOn": None}}}}
    return await db.monthlyreport.find_many(where=where, include={"athlete": True})


@router.post("/reports/{report_id}/publish")
async def publish_report(report_id: str, body: ReportPublish, user: Coaching):
    """Koç yorumu olmadan rapor veliye gitmez — sayılar bağlamsız yanlış okunur."""
    data: dict = {"coachComment": body.coachComment, "publishedAt": utcnow()}
    if user.staff_id:
        data["publishedById"] = user.staff_id
    return await db.monthlyreport.update(where={"id": report_id}, data=data)
