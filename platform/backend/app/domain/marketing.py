"""Pazarlama hunisi ve ROI metrikleri.

Tanımlar (dashboard'da da aynen gösterilir, tartışmayı önler):
  CPL            = harcama / lead
  CAC            = harcama / kazanılan üye
  ROAS           = tahsil edilen atfedilmiş gelir / harcama
  ROI            = (atfedilmiş gelir − harcama) / harcama
  LTV            = ortalama net aylık aidat × beklenen üyelik süresi (ay)
  LTV:CAC        = LTV / CAC (sağlıklı eşik ≥ 3)
  Geri ödeme     = CAC / ortalama net aylık aidat (ay)

Atıf modeli: first-touch (lead'in geldiği ilk kampanya). Kulübe gelen lead'lerin
çoğu tek temaslı form doldurma olduğundan bu ölçekte yeterlidir.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .money import ZERO, D, money

STAGE_ORDER = ("NEW", "CONTACTED", "TRIAL_SCHEDULED", "TRIAL_ATTENDED", "WON")


@dataclass(frozen=True)
class FunnelCounts:
    leads: int
    contacted: int
    trial_scheduled: int
    trial_attended: int
    won: int


def _rate(num: int | Decimal, den: int | Decimal) -> float | None:
    return None if not den else round(float(D(num) / D(den)) * 100, 1)


def _div(num: Decimal, den: int | Decimal) -> Decimal | None:
    return None if not den else money(D(num) / D(den))


def funnel_rates(f: FunnelCounts) -> dict[str, float | None]:
    return {
        "contactRate": _rate(f.contacted, f.leads),
        "trialBookRate": _rate(f.trial_scheduled, f.contacted),
        "trialShowRate": _rate(f.trial_attended, f.trial_scheduled),
        "trialToMemberRate": _rate(f.won, f.trial_attended),
        "leadToMemberRate": _rate(f.won, f.leads),
    }


@dataclass(frozen=True)
class RoiInput:
    spend: Decimal
    leads: int
    won: int
    attributed_revenue: Decimal  # dönem içinde kazanılan üyelerden tahsil edilen
    avg_monthly_fee: Decimal  # aktif aboneliklerin ortalama net aidatı
    expected_tenure_months: Decimal  # tarihsel churn'den: 1 / aylık churn oranı


def roi_metrics(r: RoiInput) -> dict[str, object]:
    spend = money(r.spend)
    cac = _div(spend, r.won)
    ltv = money(D(r.avg_monthly_fee) * D(r.expected_tenure_months))
    return {
        "spend": spend,
        "cpl": _div(spend, r.leads),
        "cac": cac,
        "roas": None if spend == ZERO else round(float(D(r.attributed_revenue) / spend), 2),
        "roi": None if spend == ZERO else round(float((D(r.attributed_revenue) - spend) / spend) * 100, 1),
        "ltv": ltv,
        "ltvToCac": None if not cac else round(float(ltv / cac), 2),
        "paybackMonths": None if not cac or not r.avg_monthly_fee else round(float(cac / D(r.avg_monthly_fee)), 1),
    }


def expected_tenure_months(monthly_churn_rate: float, cap: float = 36.0) -> Decimal:
    """Sabit churn varsayımıyla beklenen üyelik süresi = 1 / churn. Aşırı iyimserliğe karşı sınırlı."""
    if monthly_churn_rate <= 0:
        return D(cap)
    return D(round(min(1 / monthly_churn_rate, cap), 1))
