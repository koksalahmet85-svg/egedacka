"""Yönetim paneli: finans + pazarlama ROI tek yanıtta.

Tasarım kararları:
  * Tek endpoint (BFF): frontend 1 istek atar, 4 SQL paralel çalışır (asyncio.gather).
  * Toplamlar veritabanında hesaplanır; Python'a satır taşınmaz (750 sporcu ölçeğinde <50 ms).
  * Sonuç (from, to) anahtarıyla kısa süre önbelleklenir; ödeme kaydında önbellek temizlenir.
  * Kohort ROI: dönemde oluşan lead'ler → bugüne kadar tahsil edilen gelirleri.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, date, datetime
from decimal import Decimal

from ..core.config import get_settings
from ..core.db import db
from ..domain.marketing import FunnelCounts, RoiInput, expected_tenure_months, funnel_rates, roi_metrics
from ..domain.money import D

_cache: dict[tuple[date, date], tuple[float, dict]] = {}


def invalidate_cache() -> None:
    _cache.clear()


FINANCE_KPIS = """
SELECT
  (SELECT COALESCE(SUM("amount"), 0) FROM "Payment"
     WHERE "status" = 'COMPLETED' AND "paidAt" >= $1::timestamp AND "paidAt" < $2::timestamp)::float8 AS revenue,
  (SELECT COALESCE(SUM("amount"), 0) FROM "Expense"
     WHERE "incurredOn" >= $1::date AND "incurredOn" < $2::date)::float8 AS opex,
  (SELECT COALESCE(SUM("spend"), 0) FROM "AdSpendDaily"
     WHERE "date" >= $1::date AND "date" < $2::date)::float8 AS ad_spend,
  (SELECT COALESCE(SUM("netAmount"), 0) FROM "Charge"
     WHERE "status" NOT IN ('CANCELLED', 'WAIVED') AND "dueDate" >= $1::date AND "dueDate" < $2::date)::float8 AS billed,
  (SELECT COALESCE(SUM("paidAmount"), 0) FROM "Charge"
     WHERE "status" NOT IN ('CANCELLED', 'WAIVED') AND "dueDate" >= $1::date AND "dueDate" < $2::date)::float8 AS billed_collected,
  (SELECT COALESCE(SUM("netAmount" - "paidAmount"), 0) FROM "Charge" WHERE "status" = 'OVERDUE')::float8 AS overdue_amount,
  (SELECT COUNT(*) FROM "Charge" WHERE "status" = 'OVERDUE')::int AS overdue_count,
  (SELECT COUNT(DISTINCT "guardianId") FROM "Charge" WHERE "status" = 'OVERDUE')::int AS overdue_families,
  (SELECT COALESCE(SUM("netAmount" - "paidAmount"), 0) FROM "Charge"
     WHERE "status" = 'OVERDUE' AND "dueDate" < (CURRENT_DATE - 30))::float8 AS overdue_30_plus,
  (SELECT COALESCE(SUM(fp."monthlyAmount" * (100 - s."discountPct") / 100), 0)
     FROM "Subscription" s JOIN "FeePlan" fp ON fp."id" = s."feePlanId"
     WHERE s."status" = 'ACTIVE')::float8 AS mrr,
  (SELECT COUNT(*) FROM "Subscription" WHERE "status" = 'ACTIVE')::int AS active_subscriptions,
  (SELECT COUNT(*) FROM "Athlete" WHERE "status" = 'ACTIVE')::int AS active_athletes,
  (SELECT COUNT(*) FROM "Athlete" WHERE "leftOn" >= (CURRENT_DATE - 90))::int AS left_last_90d
"""

MONTHLY_SERIES = """
WITH months AS (
  SELECT generate_series(
    date_trunc('month', $1::timestamp),
    date_trunc('month', $2::timestamp - interval '1 day'),
    interval '1 month'
  ) AS m
)
SELECT
  to_char(m, 'YYYY-MM') AS month,
  COALESCE((SELECT SUM(p."amount") FROM "Payment" p WHERE p."status" = 'COMPLETED'
            AND p."paidAt" >= m AND p."paidAt" < m + interval '1 month'), 0)::float8 AS income,
  COALESCE((SELECT SUM(e."amount") FROM "Expense" e
            WHERE e."incurredOn" >= m AND e."incurredOn" < m + interval '1 month'), 0)::float8 AS opex,
  COALESCE((SELECT SUM(a."spend") FROM "AdSpendDaily" a
            WHERE a."date" >= m AND a."date" < m + interval '1 month'), 0)::float8 AS ad_spend,
  (SELECT COUNT(*) FROM "Lead" l WHERE l."createdAt" >= m AND l."createdAt" < m + interval '1 month')::int AS leads,
  (SELECT COUNT(*) FROM "Lead" l WHERE l."wonAt" >= m AND l."wonAt" < m + interval '1 month')::int AS won
FROM months ORDER BY m
"""

# Kohort hunisi: dönemde oluşan lead'ler hangi aşamaya ulaştı (LOST olsalar bile).
FUNNEL_BY_CHANNEL = """
SELECT
  l."source"::text AS channel,
  COUNT(*)::int AS leads,
  COUNT(l."firstContactAt")::int AS contacted,
  COUNT(l."trialScheduledAt")::int AS trial_scheduled,
  COUNT(l."trialAttendedAt")::int AS trial_attended,
  COUNT(l."wonAt")::int AS won,
  COUNT(*) FILTER (WHERE l."stage" = 'LOST')::int AS lost,
  (percentile_cont(0.5) WITHIN GROUP (
     ORDER BY EXTRACT(EPOCH FROM (l."firstContactAt" - l."createdAt")) / 60.0))::float8 AS median_response_min
FROM "Lead" l
WHERE l."createdAt" >= $1::timestamp AND l."createdAt" < $2::timestamp
GROUP BY l."source"
ORDER BY leads DESC
"""

CAMPAIGNS = """
WITH spend AS (
  SELECT "campaignId", SUM("spend") AS spend, SUM("impressions") AS impressions, SUM("clicks") AS clicks
  FROM "AdSpendDaily" WHERE "date" >= $1::date AND "date" < $2::date
  GROUP BY 1
), other_cost AS (
  SELECT "campaignId", SUM("amount") AS amount
  FROM "Expense" WHERE "campaignId" IS NOT NULL AND "incurredOn" >= $1::date AND "incurredOn" < $2::date
  GROUP BY 1
), cohort AS (
  SELECT "campaignId", COUNT(*) AS leads, COUNT("trialAttendedAt") AS trials, COUNT("wonAt") AS won
  FROM "Lead" WHERE "campaignId" IS NOT NULL AND "createdAt" >= $1::timestamp AND "createdAt" < $2::timestamp
  GROUP BY 1
), revenue AS (
  SELECT v.campaign_id, SUM(v.amount) AS revenue
  FROM "v_lead_revenue" v JOIN "Lead" l ON l."id" = v.lead_id
  WHERE l."createdAt" >= $1::timestamp AND l."createdAt" < $2::timestamp
  GROUP BY 1
)
SELECT
  c."id" AS id, c."name" AS name, c."platform"::text AS platform,
  (COALESCE(s.spend, 0) + COALESCE(o.amount, 0))::float8 AS spend,
  COALESCE(s.impressions, 0)::int AS impressions,
  COALESCE(s.clicks, 0)::int AS clicks,
  COALESCE(co.leads, 0)::int AS leads,
  COALESCE(co.trials, 0)::int AS trials,
  COALESCE(co.won, 0)::int AS won,
  COALESCE(r.revenue, 0)::float8 AS revenue
FROM "AdCampaign" c
LEFT JOIN spend s       ON s."campaignId" = c."id"
LEFT JOIN other_cost o  ON o."campaignId" = c."id"
LEFT JOIN cohort co     ON co."campaignId" = c."id"
LEFT JOIN revenue r     ON r.campaign_id = c."id"
WHERE s."campaignId" IS NOT NULL OR o."campaignId" IS NOT NULL OR co."campaignId" IS NOT NULL
ORDER BY spend DESC, leads DESC
"""


def _pct(a: float, b: float) -> float | None:
    return None if not b else round(a / b * 100, 1)


def _f(x: Decimal | None) -> float | None:
    return None if x is None else float(x)


def _roi_block(spend: float, leads: int, won: int, revenue: float, avg_fee: float, tenure: Decimal) -> dict:
    m = roi_metrics(
        RoiInput(
            spend=D(spend),
            leads=leads,
            won=won,
            attributed_revenue=D(revenue),
            avg_monthly_fee=D(avg_fee),
            expected_tenure_months=tenure,
        )
    )
    return {k: (_f(v) if isinstance(v, Decimal) else v) for k, v in m.items()}


async def overview(date_from: date, date_to: date) -> dict:
    """date_to hariç (yarı açık aralık)."""
    key = (date_from, date_to)
    ttl = get_settings().dashboard_cache_seconds
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]

    a, b = date_from.isoformat(), date_to.isoformat()
    kpi_rows, series, channels, campaigns = await asyncio.gather(
        db.query_raw(FINANCE_KPIS, a, b),
        db.query_raw(MONTHLY_SERIES, a, b),
        db.query_raw(FUNNEL_BY_CHANNEL, a, b),
        db.query_raw(CAMPAIGNS, a, b),
    )
    k = kpi_rows[0]

    # ── Finans ──
    total_expenses = k["opex"] + k["ad_spend"]
    net = k["revenue"] - total_expenses
    avg_fee = k["mrr"] / k["active_subscriptions"] if k["active_subscriptions"] else 0.0
    churn = (k["left_last_90d"] / 3) / k["active_athletes"] if k["active_athletes"] else 0.0
    tenure = expected_tenure_months(churn, cap=36.0) if churn else D(get_settings().default_expected_tenure_months)

    finance = {
        "revenue": k["revenue"],
        "operatingExpenses": k["opex"],
        "adSpend": k["ad_spend"],
        "totalExpenses": total_expenses,
        "net": net,
        "marginPct": _pct(net, k["revenue"]),
        "billed": k["billed"],
        "collectionRatePct": _pct(k["billed_collected"], k["billed"]),
        "overdue": {
            "amount": k["overdue_amount"],
            "count": k["overdue_count"],
            "families": k["overdue_families"],
            "over30DaysAmount": k["overdue_30_plus"],
        },
        "mrr": k["mrr"],
        "activeAthletes": k["active_athletes"],
        "avgMonthlyFee": round(avg_fee, 2),
        "monthlyChurnPct": round(churn * 100, 2),
        "series": [{**r, "net": r["income"] - r["opex"] - r["ad_spend"]} for r in series],
    }

    # ── Pazarlama ──
    tot = FunnelCounts(
        leads=sum(c["leads"] for c in channels),
        contacted=sum(c["contacted"] for c in channels),
        trial_scheduled=sum(c["trial_scheduled"] for c in channels),
        trial_attended=sum(c["trial_attended"] for c in channels),
        won=sum(c["won"] for c in channels),
    )
    paid_spend = sum(c["spend"] for c in campaigns)
    paid_leads = sum(c["leads"] for c in campaigns)
    paid_won = sum(c["won"] for c in campaigns)
    paid_revenue = sum(c["revenue"] for c in campaigns)

    marketing = {
        "funnel": {
            "leads": tot.leads,
            "contacted": tot.contacted,
            "trialScheduled": tot.trial_scheduled,
            "trialAttended": tot.trial_attended,
            "won": tot.won,
            **funnel_rates(tot),
        },
        "paid": {
            "leads": paid_leads,
            "won": paid_won,
            "attributedRevenue": paid_revenue,
            **_roi_block(paid_spend, paid_leads, paid_won, paid_revenue, avg_fee, tenure),
        },
        "expectedTenureMonths": float(tenure),
        "channels": [
            {
                "channel": c["channel"],
                "leads": c["leads"],
                "contacted": c["contacted"],
                "trialScheduled": c["trial_scheduled"],
                "trialAttended": c["trial_attended"],
                "won": c["won"],
                "lost": c["lost"],
                "leadToMemberPct": _pct(c["won"], c["leads"]),
                "medianResponseMin": None if c["median_response_min"] is None else round(c["median_response_min"], 0),
            }
            for c in channels
        ],
        "campaigns": [
            {
                "id": c["id"],
                "name": c["name"],
                "platform": c["platform"],
                "spend": c["spend"],
                "impressions": c["impressions"],
                "clicks": c["clicks"],
                "ctrPct": _pct(c["clicks"], c["impressions"]),
                "leads": c["leads"],
                "trials": c["trials"],
                "won": c["won"],
                "revenue": c["revenue"],
                **{
                    k2: v
                    for k2, v in _roi_block(c["spend"], c["leads"], c["won"], c["revenue"], avg_fee, tenure).items()
                    if k2 in ("cpl", "cac", "roas", "roi", "ltvToCac")
                },
            }
            for c in campaigns
        ],
    }

    # ── Finans × Pazarlama köprüsü ──
    combined = {
        "adSpendShareOfRevenuePct": _pct(k["ad_spend"], k["revenue"]),
        "newMrrFromMarketing": round(tot.won * avg_fee, 2),
        "marketingPaybackMonths": marketing["paid"]["paybackMonths"],
    }

    result = {
        "range": {"from": a, "to": b},
        "generatedAt": datetime.now(UTC).isoformat(),
        "finance": finance,
        "marketing": marketing,
        "combined": combined,
    }
    if len(_cache) > 64:  # rastgele tarih aralıklarıyla bellek şişmesin
        _cache.clear()
    _cache[key] = (time.monotonic(), result)
    return result
