"""Sporcu gelişim analitiği ve aylık veli raporu."""
from __future__ import annotations

from datetime import date, timedelta

import asyncpg

from ..core.config import get_settings
from . import analytics as an


def _age(birth: date, on: date) -> float:
    return (on - birth).days / 365.25


async def metric_progress(conn: asyncpg.Connection, athlete_id: int) -> list[dict]:
    """Her metrik için son iki ölçüm, değişim, SWC kararı ve yaş grubu z-skoru.

    SWC ve z-skoru aynı doğum yılındaki sporcuların SON ölçümlerinden hesaplanır →
    U16 ile U10 birbirine kıyaslanmaz.
    """
    recs = await conn.fetch(
        """WITH me AS (SELECT birth_date FROM athletes WHERE id = $1),
           ranked AS (
             SELECT m.metric_id, a.athlete_id, m.value::float8 AS value, a.assessed_at,
                    row_number() OVER (PARTITION BY a.athlete_id, m.metric_id ORDER BY a.assessed_at DESC) AS rn
             FROM measurements m JOIN assessments a ON a.id = m.assessment_id
             JOIN athletes ath ON ath.id = a.athlete_id
             WHERE extract(year FROM ath.birth_date) = (SELECT extract(year FROM birth_date) FROM me)),
           peers AS (SELECT metric_id, array_agg(value) AS vals FROM ranked WHERE rn = 1 GROUP BY metric_id)
           SELECT md.id, md.code, md.name, md.unit, md.category, md.higher_is_better,
                  md.typical_error::float8 AS typical_error,
                  cur.value AS current, cur.assessed_at AS current_at,
                  prev.value AS previous, prev.assessed_at AS previous_at, p.vals AS peer_values
           FROM metric_definitions md
           JOIN ranked cur ON cur.metric_id = md.id AND cur.athlete_id = $1 AND cur.rn = 1
           LEFT JOIN ranked prev ON prev.metric_id = md.id AND prev.athlete_id = $1 AND prev.rn = 2
           LEFT JOIN peers p ON p.metric_id = md.id
           ORDER BY md.category, md.code""",
        athlete_id)
    out = []
    for r in recs:
        peers = list(r["peer_values"] or [])
        swc_v = an.swc(peers)
        delta = r["current"] - r["previous"] if r["previous"] is not None else None
        out.append({
            "code": r["code"], "name": r["name"], "unit": r["unit"], "category": r["category"],
            "current": r["current"], "current_at": r["current_at"],
            "previous": r["previous"], "previous_at": r["previous_at"],
            "delta": delta, "swc": swc_v,
            "verdict": an.classify_change(delta, swc_v, r["typical_error"], r["higher_is_better"])
            if delta is not None else None,
            "z_age_group": an.zscore(r["current"], peers, r["higher_is_better"]),
            "peer_n": len(peers),
        })
    return out


async def attendance_trend(conn: asyncpg.Connection, athlete_id: int, weeks: int = 12) -> list[dict]:
    """Haftalık devam oranı + sRPE yükü. Mazeretli devamsızlık paydadan düşülmez
    (yük planlaması için gerçek katılımı gösterir) ama ayrıca raporlanır."""
    tz = get_settings().timezone
    recs = await conn.fetch(
        """SELECT date_trunc('week', s.starts_at AT TIME ZONE $3)::date AS week,
                  COUNT(*) AS sessions,
                  COUNT(*) FILTER (WHERE a.status IN ('PRESENT','LATE')) AS attended,
                  COUNT(*) FILTER (WHERE a.status = 'EXCUSED') AS excused,
                  SUM(COALESCE(a.rpe,0) * COALESCE(a.minutes,
                      EXTRACT(EPOCH FROM s.ends_at - s.starts_at)::int / 60))
                    FILTER (WHERE a.status IN ('PRESENT','LATE')) AS load
           FROM attendances a JOIN training_sessions s ON s.id = a.session_id
           WHERE a.athlete_id = $1 AND s.status = 'COMPLETED'
             AND s.starts_at >= now() - make_interval(weeks => $2)
           GROUP BY 1 ORDER BY 1""",
        athlete_id, weeks, tz)
    return [dict(r) | {"rate": an.safe_div(r["attended"], r["sessions"])} for r in recs]


async def game_averages(conn: asyncpg.Connection, athlete_id: int, since: date | None = None) -> dict:
    r = await conn.fetchrow(
        """SELECT COUNT(*) AS games, SUM(minutes) AS min, SUM(pts) AS pts, SUM(fgm) AS fgm, SUM(fga) AS fga,
                  SUM(tpm) AS tpm, SUM(tpa) AS tpa, SUM(ftm) AS ftm, SUM(fta) AS fta,
                  SUM(oreb + dreb) AS reb, SUM(ast) AS ast, SUM(stl) AS stl, SUM(blk) AS blk, SUM(tov) AS tov
           FROM game_stats gs JOIN games g ON g.id = gs.game_id
           WHERE gs.athlete_id = $1 AND ($2::date IS NULL OR g.played_at >= $2)""",
        athlete_id, since)
    n = r["games"] or 0
    if n == 0:
        return {"games": 0}
    per = {k: round(r[k] / n, 1) for k in ("min", "pts", "reb", "ast", "stl", "blk", "tov")}
    return {"games": n, **per,
            **an.shooting_efficiency(r["pts"], r["fgm"], r["fga"], r["tpm"], r["fta"]),
            "ast_tov": an.safe_div(r["ast"], r["tov"])}


async def maturity(conn: asyncpg.Connection, athlete_id: int) -> dict | None:
    r = await conn.fetchrow(
        """SELECT ath.gender, ath.birth_date,
             (SELECT m.value::float8 FROM measurements m JOIN assessments a ON a.id=m.assessment_id
              JOIN metric_definitions d ON d.id=m.metric_id
              WHERE a.athlete_id=ath.id AND d.code='boy' ORDER BY a.assessed_at DESC LIMIT 1) AS height,
             (SELECT m.value::float8 FROM measurements m JOIN assessments a ON a.id=m.assessment_id
              JOIN metric_definitions d ON d.id=m.metric_id
              WHERE a.athlete_id=ath.id AND d.code='oturma_boyu' ORDER BY a.assessed_at DESC LIMIT 1) AS sitting
           FROM athletes ath WHERE ath.id=$1""", athlete_id)
    if r is None:
        return None
    off = an.maturity_offset(r["gender"], _age(r["birth_date"], date.today()), r["height"], r["sitting"])
    return {"offset_years": round(off, 2) if off is not None else None,
            "status": an.maturity_status(off),
            "birth_quarter": an.birth_quarter(r["birth_date"].month)}


async def build_monthly_report(conn: asyncpg.Connection, athlete_id: int, period: date) -> dict:
    """Ay snapshot'ı üretip performance_reports'a yazar (yayımlanmışsa dokunmaz)."""
    period = period.replace(day=1)
    nxt = (period + timedelta(days=32)).replace(day=1)
    tz = get_settings().timezone
    att = await conn.fetchrow(
        """SELECT COUNT(*) AS sessions,
                  COUNT(*) FILTER (WHERE a.status IN ('PRESENT','LATE')) AS attended,
                  COUNT(*) FILTER (WHERE a.status = 'EXCUSED') AS excused,
                  AVG(a.rpe) FILTER (WHERE a.rpe IS NOT NULL)::float8 AS avg_rpe
           FROM attendances a JOIN training_sessions s ON s.id = a.session_id
           WHERE a.athlete_id = $1 AND s.status = 'COMPLETED'
             AND (s.starts_at AT TIME ZONE $4)::date >= $2 AND (s.starts_at AT TIME ZONE $4)::date < $3""",
        athlete_id, period, nxt, tz)
    summary = {
        "period": period.isoformat(),
        "attendance": dict(att) | {"rate": an.safe_div(att["attended"], att["sessions"])},
        "metrics": await metric_progress(conn, athlete_id),
        "games": await game_averages(conn, athlete_id, period),
        "maturity": await maturity(conn, athlete_id),
    }
    summary = _jsonable(summary)
    await conn.execute(
        """INSERT INTO performance_reports (athlete_id, period, summary) VALUES ($1,$2,$3::jsonb)
           ON CONFLICT (athlete_id, period) DO UPDATE SET summary = EXCLUDED.summary
           WHERE performance_reports.published_at IS NULL""",
        athlete_id, period, summary)
    return summary


def _jsonable(o):
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_jsonable(v) for v in o]
    if isinstance(o, date):
        return o.isoformat()
    if hasattr(o, "__float__") and not isinstance(o, (int, float, bool)):
        return float(o)
    return o
