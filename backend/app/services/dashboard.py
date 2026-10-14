"""Yönetici paneli: finans + pazarlama ROI tek yanıtta.

Tasarım kararları:
- Tek endpoint, tek round-trip: frontend'de istek şelalesi (waterfall) yok.
- Alt sorgular havuzdan ayrı bağlantılarla PARALEL çalışır (asyncio.gather).
- Kohort mantığı: huni, seçilen aralıkta OLUŞAN lead'leri bugüne kadar izler.
  (Aralıkta kazanılanları aralıkta gelen lead'lere bölmek oranı şişirir.)
- Gerçekleşen ROAS (tahsil edilen) ve öngörülen ROI (LTV) ayrı raporlanır:
  aidat aylık geldiği için yeni kampanyada ROAS doğal olarak düşük başlar.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from ..core.config import get_settings
from ..core.db import pool
from . import analytics as an

_cache: dict[tuple, tuple[float, dict]] = {}


async def _q(sql: str, *args) -> list[dict[str, Any]]:
    async with pool().acquire() as conn:
        return [dict(r) for r in await conn.fetch(sql, *args)]


_FIN_TOTALS = """
SELECT
  (SELECT COALESCE(SUM(amount),0) FROM payments WHERE paid_at::date BETWEEN $1 AND $2)::float8 AS collected,
  (SELECT COALESCE(SUM(total),0) FROM invoices
     WHERE status NOT IN ('CANCELLED','DRAFT') AND issue_date BETWEEN $1 AND $2)::float8 AS invoiced,
  (SELECT COALESCE(SUM(paid_amount),0) FROM invoices
     WHERE status NOT IN ('CANCELLED','DRAFT') AND issue_date BETWEEN $1 AND $2)::float8 AS invoiced_collected,
  (SELECT COALESCE(SUM(amount),0) FROM expenses WHERE spent_at BETWEEN $1 AND $2)::float8 AS expenses,
  (SELECT COALESCE(SUM(employer_cost),0) FROM payrolls WHERE status='PAID' AND paid_at::date BETWEEN $1 AND $2)::float8 AS payroll,
  (SELECT COUNT(*) FROM athletes WHERE status='ACTIVE') AS active_athletes,
  (SELECT COALESCE(SUM(total),0) FROM invoices
     WHERE status NOT IN ('CANCELLED','DRAFT') AND period = (SELECT MAX(period) FROM invoices))::float8 AS mrr
"""

_OVERDUE = """
SELECT CASE WHEN days_overdue <= 7 THEN '1-7' WHEN days_overdue <= 30 THEN '8-30'
            WHEN days_overdue <= 60 THEN '31-60' ELSE '60+' END AS bucket,
       COUNT(*) AS count, SUM(balance)::float8 AS amount
FROM v_invoice_balance WHERE is_overdue AND balance > 0
GROUP BY 1 ORDER BY MIN(days_overdue)
"""

_CASHFLOW_MONTHLY = """
SELECT to_char(date_trunc('month', day), 'YYYY-MM') AS month,
       SUM(amount) FILTER (WHERE direction='INCOME')::float8 AS income,
       SUM(amount) FILTER (WHERE direction='EXPENSE' AND category <> 'PAYROLL')::float8 AS expenses,
       SUM(amount) FILTER (WHERE category='PAYROLL')::float8 AS payroll
FROM v_cash_movements WHERE day BETWEEN $1 AND $2
GROUP BY 1 ORDER BY 1
"""

# Kampanya bazında harcama + kohort hunisi + kazanılan sporculardan tahsilat.
_CAMPAIGNS = """
WITH spend AS (
  SELECT campaign_id, SUM(spend) AS spend, SUM(clicks) AS clicks, SUM(impressions) AS impressions
  FROM ad_spend_daily WHERE date BETWEEN $1 AND $2 GROUP BY 1
  UNION ALL
  SELECT campaign_id, SUM(amount), 0, 0 FROM expenses
  WHERE campaign_id IS NOT NULL AND spent_at BETWEEN $1 AND $2 GROUP BY 1),
spend_c AS (SELECT campaign_id, SUM(spend) AS spend, SUM(clicks) AS clicks, SUM(impressions) AS impressions
            FROM spend GROUP BY 1),
cohort AS (
  SELECT l.id, l.campaign_id, l.athlete_id, l.first_contact_at, l.converted_at,
         EXISTS (SELECT 1 FROM trial_bookings t WHERE t.lead_id = l.id) AS trial_booked,
         EXISTS (SELECT 1 FROM trial_bookings t WHERE t.lead_id = l.id AND t.status = 'ATTENDED') AS trial_attended
  FROM leads l WHERE l.created_at::date BETWEEN $1 AND $2),
funnel AS (
  SELECT campaign_id, COUNT(*) AS leads,
         COUNT(*) FILTER (WHERE first_contact_at IS NOT NULL) AS contacted,
         COUNT(*) FILTER (WHERE trial_booked) AS trials_booked,
         COUNT(*) FILTER (WHERE trial_attended) AS trials,
         COUNT(athlete_id) AS won
  FROM cohort GROUP BY 1),
revenue AS (
  SELECT c.campaign_id, SUM(p.amount) AS revenue
  FROM cohort c JOIN invoices i ON i.athlete_id = c.athlete_id
  JOIN payments p ON p.invoice_id = i.id AND p.paid_at >= c.converted_at  -- yalnız kayıt sonrası gelir
  GROUP BY 1)
SELECT cp.id, cp.name, cp.channel::text,
       COALESCE(s.spend,0)::float8 AS spend, COALESCE(s.clicks,0) AS clicks,
       COALESCE(s.impressions,0) AS impressions,
       COALESCE(f.leads,0) AS leads, COALESCE(f.contacted,0) AS contacted,
       COALESCE(f.trials_booked,0) AS trials_booked, COALESCE(f.trials,0) AS trials,
       COALESCE(f.won,0) AS won, COALESCE(r.revenue,0)::float8 AS revenue
FROM campaigns cp
LEFT JOIN spend_c s ON s.campaign_id = cp.id
LEFT JOIN funnel f  ON f.campaign_id = cp.id
LEFT JOIN revenue r ON r.campaign_id = cp.id
WHERE s.spend IS NOT NULL OR f.leads IS NOT NULL
UNION ALL
-- Kampanyasız lead'ler (tavsiye, walk-in): harcaması 0 ama huniye dahil.
SELECT NULL, 'Kampanyasız / organik', 'ORGANIC', 0, 0, 0,
       COALESCE(f.leads,0), COALESCE(f.contacted,0), COALESCE(f.trials_booked,0),
       COALESCE(f.trials,0), COALESCE(f.won,0), COALESCE(r.revenue,0)::float8
FROM (SELECT 1) one
LEFT JOIN funnel f ON f.campaign_id IS NULL
LEFT JOIN revenue r ON r.campaign_id IS NULL
WHERE f.leads IS NOT NULL
"""

_LEAD_OPS = """
SELECT
  (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY EXTRACT(EPOCH FROM first_contact_at - created_at) / 60)
     FROM leads WHERE first_contact_at IS NOT NULL AND created_at::date BETWEEN $1 AND $2)::float8
     AS median_minutes_to_contact,
  (SELECT COUNT(*) FROM leads WHERE first_contact_at IS NULL AND stage = 'NEW'
     AND created_at < now() - interval '24 hours') AS uncontacted_24h
"""

# Ortalama aylık net aidat (son dönem) ve ayrılan sporcuların kulüpte kalma süresi → LTV.
_LTV_INPUTS = """
SELECT
  (SELECT AVG(total) FROM invoices WHERE status NOT IN ('CANCELLED','DRAFT')
     AND period = (SELECT MAX(period) FROM invoices))::float8 AS avg_monthly,
  (SELECT COALESCE(array_agg((left_at - joined_at) / 30.44), '{}') FROM athletes
     WHERE status = 'LEFT' AND left_at IS NOT NULL)::float8[] AS tenures
"""

_ALERTS = """
SELECT
  (SELECT COUNT(*) FROM athletes WHERE status='ACTIVE' AND
     (health_report_expires_at IS NULL OR health_report_expires_at < CURRENT_DATE + 30)) AS health_reports_expiring,
  (SELECT COUNT(*) FROM v_invoice_balance WHERE is_overdue AND days_overdue > 30) AS invoices_over_30d,
  (SELECT COUNT(*) FROM training_sessions WHERE status='PLANNED' AND ends_at < now() - interval '24 hours')
     AS sessions_missing_attendance,
  (SELECT COUNT(*) FROM notification_outbox WHERE status='FAILED' AND attempts >= 5) AS failed_notifications
"""


async def executive_summary(date_from: date, date_to: date) -> dict:
    key = (date_from, date_to)
    ttl = get_settings().dashboard_cache_seconds
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]

    fin, overdue, monthly, camps, ops, ltv_in, alerts = await asyncio.gather(
        _q(_FIN_TOTALS, date_from, date_to), _q(_OVERDUE), _q(_CASHFLOW_MONTHLY, date_from, date_to),
        _q(_CAMPAIGNS, date_from, date_to), _q(_LEAD_OPS, date_from, date_to), _q(_LTV_INPUTS), _q(_ALERTS))

    f = fin[0]
    net = f["collected"] - f["expenses"] - f["payroll"]
    lifetime = an.lifetime_months(ltv_in[0]["tenures"] or [], get_settings().default_lifetime_months)
    avg_monthly = ltv_in[0]["avg_monthly"]

    campaigns = []
    for c in camps:
        k = an.marketing_kpis(c["spend"], c["leads"], c["trials"], c["won"], c["revenue"], avg_monthly, lifetime)
        campaigns.append({"id": c["id"], "name": c["name"], "channel": c["channel"],
                          "clicks": c["clicks"], "impressions": c["impressions"],
                          "ctr": an.safe_div(c["clicks"], c["impressions"]), **asdict(k)})
    tot = {k: sum(c[k] for c in camps) for k in ("spend", "leads", "contacted", "trials_booked", "trials",
                                                 "won", "revenue")}
    total_kpis = an.marketing_kpis(tot["spend"], tot["leads"], tot["trials"], tot["won"], tot["revenue"],
                                   avg_monthly, lifetime)
    campaigns.sort(key=lambda c: (c["projected_roi"] is None, -(c["projected_roi"] or 0)))

    result = {
        "range": {"from": date_from.isoformat(), "to": date_to.isoformat()},
        "finance": {
            "collected": f["collected"], "invoiced": f["invoiced"],
            "collection_rate": an.safe_div(f["invoiced_collected"], f["invoiced"]),
            "expenses": f["expenses"], "payroll": f["payroll"], "net_cashflow": net,
            "margin": an.safe_div(net, f["collected"]), "mrr": f["mrr"],
            "active_athletes": f["active_athletes"],
            "arpa": an.safe_div(f["mrr"], f["active_athletes"]),  # sporcu başı ortalama gelir
            "overdue": {"total": sum(o["amount"] for o in overdue),
                        "count": sum(o["count"] for o in overdue), "buckets": overdue},
            "monthly": [{**m, "income": m["income"] or 0, "expenses": m["expenses"] or 0,
                         "payroll": m["payroll"] or 0,
                         "net": (m["income"] or 0) - (m["expenses"] or 0) - (m["payroll"] or 0)}
                        for m in monthly],
        },
        "marketing": {
            **asdict(total_kpis),
            "lifetime_months": lifetime,
            "funnel": [
                {"stage": "LEAD", "count": tot["leads"]},
                {"stage": "CONTACTED", "count": tot["contacted"]},
                {"stage": "TRIAL_BOOKED", "count": tot["trials_booked"]},
                {"stage": "TRIAL_ATTENDED", "count": tot["trials"]},
                {"stage": "WON", "count": tot["won"]},
            ],
            "median_minutes_to_contact": ops[0]["median_minutes_to_contact"],
            "uncontacted_24h": ops[0]["uncontacted_24h"],
            "campaigns": campaigns,
        },
        "alerts": alerts[0],
    }
    if len(_cache) > 64:  # farklı tarih aralıklarıyla bellek şişmesin
        _cache.clear()
    _cache[key] = (time.monotonic(), result)
    return result


def default_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    start = (today.replace(day=1) - timedelta(days=150)).replace(day=1)  # son 6 ay
    return start, today
