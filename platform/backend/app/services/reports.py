"""Aylık sporcu performans raporu (snapshot) üretimi. Tüm kulüp için 3 sorgu, N+1 yok."""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from prisma import Json

from ..core.db import db
from ..core.timeutil import as_dt, month_bounds
from ..domain.money import D
from ..domain.performance import attendance_rate, change_verdict, swc

ATTENDANCE_SQL = """
WITH sess AS (
  SELECT ts."id", ts."teamId", ts."startsAt", ts."endsAt"
  FROM "TrainingSession" ts
  WHERE ts."status" = 'COMPLETED' AND ts."type" <> 'TRIAL'
    AND ts."startsAt" >= $1::timestamp AND ts."startsAt" < $2::timestamp
)
SELECT tm."athleteId" AS athlete_id,
       COUNT(DISTINCT s."id")::int AS total,
       COUNT(DISTINCT s."id") FILTER (WHERE a."status" IN ('PRESENT', 'LATE'))::int AS attended,
       COALESCE(SUM(a."rpe" * COALESCE(a."minutes",
           (EXTRACT(EPOCH FROM (s."endsAt" - s."startsAt")) / 60)::int)), 0)::int AS load_au
FROM sess s
JOIN "TeamMembership" tm ON tm."teamId" = s."teamId"
  AND tm."joinedOn" <= s."startsAt"::date AND (tm."leftOn" IS NULL OR tm."leftOn" > s."startsAt"::date)
JOIN "Athlete" ath ON ath."id" = tm."athleteId" AND ath."status" IN ('ACTIVE', 'PAUSED')
LEFT JOIN "Attendance" a ON a."sessionId" = s."id" AND a."athleteId" = tm."athleteId"
GROUP BY tm."athleteId"
"""

GAMES_SQL = """
SELECT gs."athleteId" AS athlete_id, COUNT(*)::int AS games,
       AVG(gs."points")::float8 AS pts, AVG(gs."oreb" + gs."dreb")::float8 AS reb, AVG(gs."ast")::float8 AS ast,
       AVG(gs."points" + gs."oreb" + gs."dreb" + gs."ast" + gs."stl" + gs."blk" + gs."foulsDrawn"
           - (gs."fga2" - gs."fgm2") - (gs."fga3" - gs."fgm3") - (gs."fta" - gs."ftm")
           - gs."tov" - gs."pf" - gs."blkAgainst")::float8 AS pir
FROM "GameStat" gs JOIN "Game" g ON g."id" = gs."gameId"
WHERE g."playedAt" >= $1::timestamp AND g."playedAt" < $2::timestamp AND gs."seconds" > 0
GROUP BY gs."athleteId"
"""

# Her sporcu × test için: ay içindeki son değer ve aydan önceki son değer.
TESTS_SQL = """
WITH ranked AS (
  SELECT r."athleteId", r."testTypeId", r."value"::float8 AS value, r."measuredAt",
         (r."measuredAt" >= $1::timestamp) AS in_period,
         ROW_NUMBER() OVER (PARTITION BY r."athleteId", r."testTypeId", (r."measuredAt" >= $1::timestamp)
                            ORDER BY r."measuredAt" DESC, r."value" DESC) AS rn
  FROM "PhysicalTestResult" r
  WHERE r."measuredAt" < $2::timestamp
)
SELECT c."athleteId" AS athlete_id, t."code" AS code, t."unit" AS unit, t."higherIsBetter" AS higher_is_better,
       t."typicalError"::float8 AS typical_error, c.value AS current, p.value AS previous
FROM ranked c
JOIN "PhysicalTestType" t ON t."id" = c."testTypeId"
LEFT JOIN ranked p ON p."athleteId" = c."athleteId" AND p."testTypeId" = c."testTypeId" AND NOT p.in_period AND p.rn = 1
WHERE c.in_period AND c.rn = 1
"""


async def generate_monthly_reports(period: date) -> int:
    start, end = month_bounds(period)
    a, b = start.isoformat(), end.isoformat()
    att = await db.query_raw(ATTENDANCE_SQL, a, b)
    games = {r["athlete_id"]: r for r in await db.query_raw(GAMES_SQL, a, b)}
    tests = await db.query_raw(TESTS_SQL, a, b)

    # SWC: o ay test edilen tüm sporcuların değer dağılımından (test bazında).
    by_code: dict[str, list[float]] = defaultdict(list)
    for t in tests:
        by_code[t["code"]].append(t["current"])
    swc_by_code = {code: swc(vals) for code, vals in by_code.items()}

    metrics: dict[str, dict] = defaultdict(dict)
    for t in tests:
        verdict = (
            change_verdict(
                t["previous"], t["current"], t["higher_is_better"], swc_by_code[t["code"]], t["typical_error"]
            )
            if t["previous"] is not None
            else "baseline"
        )
        metrics[t["athlete_id"]][t["code"]] = {
            "value": t["current"],
            "previous": t["previous"],
            "delta": None if t["previous"] is None else round(t["current"] - t["previous"], 3),
            "unit": t["unit"],
            "swc": swc_by_code[t["code"]],
            "verdict": verdict,
        }

    count = 0
    for r in att:
        aid = r["athlete_id"]
        g = games.get(aid)
        report = {
            "sessionsTotal": r["total"],
            "sessionsAttended": r["attended"],
            "attendanceRate": D(attendance_rate(r["attended"], r["total"])),
            "totalLoadAu": r["load_au"],
            "gamesPlayed": g["games"] if g else 0,
            "avgPoints": D(round(g["pts"], 2)) if g else None,
            "avgRebounds": D(round(g["reb"], 2)) if g else None,
            "avgAssists": D(round(g["ast"], 2)) if g else None,
            "avgPir": D(round(g["pir"], 2)) if g else None,
            "metrics": Json(metrics.get(aid, {})),
        }
        # Yayınlanmış rapor sessizce değişmez; sadece taslaklar yeniden hesaplanır.
        existing = await db.monthlyreport.find_unique(
            where={"athleteId_period": {"athleteId": aid, "period": as_dt(start)}}
        )
        if existing and existing.publishedAt:
            continue
        await db.monthlyreport.upsert(
            where={"athleteId_period": {"athleteId": aid, "period": as_dt(start)}},
            data={"create": {"athleteId": aid, "period": as_dt(start), **report}, "update": report},
        )
        count += 1
    return count
