"""Saf (I/O'suz) hesaplamalar — birim testlenebilir, SQL'den bağımsız.

Spor bilimi referansları:
- Seans yükü (sRPE): Foster et al. (2001) J Strength Cond Res 15(1):109-115.
- Monotoni & strain: Foster (1998) Med Sci Sports Exerc 30(7):1164-1168.
- SWC = 0.2 × sporcular arası SD: Hopkins (2004) Sportscience 8:1-7.
- Olgunlaşma ofseti (PHV'ye kalan yıl): Moore et al. (2015) Med Sci Sports Exerc
  47(8):1755-1764 — Mirwald (2002) denkleminin sadeleştirilmiş, daha az yanlı hali.
- eFG% / TS%: Oliver (2004) "Basketball on Paper".
Bilinçli olarak ACWR kullanılmadı: oran-tabanlı sakatlık tahmini metodolojik
olarak çürütüldü (Impellizzeri et al. 2020, Int J Sports Physiol Perform 15(6)).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

TWO = Decimal("0.01")


def money(x: Decimal | float | int) -> Decimal:
    return Decimal(str(x)).quantize(TWO, rounding=ROUND_HALF_UP)


def safe_div(a: float | Decimal | None, b: float | Decimal | None) -> float | None:
    if a is None or not b:
        return None
    return float(a) / float(b)


# ── Finans ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InvoiceAmounts:
    gross: Decimal  # liste fiyatı, KDV dahil
    discount: Decimal  # KDV dahil indirim tutarı
    subtotal: Decimal  # KDV hariç, indirim sonrası
    vat: Decimal
    total: Decimal  # tahsil edilecek


def invoice_amounts(monthly_amount: Decimal, vat_rate: Decimal, discount_pct: Decimal,
                    sibling_discount_pct: Decimal, sibling_rank: int) -> InvoiceAmounts:
    """Aidat tutarını hesaplar. Fiyatlar KDV dahil tanımlıdır (velinin gördüğü fiyat).

    Kardeş indirimi yalnızca aynı velinin 2. ve sonraki çocuğuna uygulanır;
    burs/özel indirimle birleşik uygulanır (çarpımsal, toplamsal değil → %100'ü aşamaz).
    """
    pct = Decimal(1) - discount_pct / 100
    if sibling_rank >= 2:
        pct *= Decimal(1) - sibling_discount_pct / 100
    total = money(monthly_amount * pct)
    subtotal = money(total / (1 + vat_rate / 100))
    return InvoiceAmounts(
        gross=money(monthly_amount), discount=money(monthly_amount) - total,
        subtotal=subtotal, vat=total - subtotal, total=total)


def overdue_bucket(days: int) -> str:
    if days <= 0:
        return "current"
    if days <= 7:
        return "1-7"
    if days <= 30:
        return "8-30"
    if days <= 60:
        return "31-60"
    return "60+"


# ── Pazarlama / ROI ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MarketingKpis:
    spend: float
    leads: int
    trials: int
    won: int
    cpl: float | None  # cost per lead
    cost_per_trial: float | None
    cac: float | None  # customer acquisition cost
    lead_to_trial: float | None
    trial_to_won: float | None
    lead_to_won: float | None
    realized_revenue: float  # kazanılan üyelerden şimdiye kadar tahsil edilen
    roas: float | None  # realized_revenue / spend
    ltv: float | None  # beklenen yaşam boyu gelir (üye başına)
    ltv_cac: float | None
    projected_roi: float | None  # (won × LTV − spend) / spend


def marketing_kpis(spend: float, leads: int, trials: int, won: int, realized_revenue: float,
                   avg_monthly_revenue: float | None, lifetime_months: float) -> MarketingKpis:
    ltv = avg_monthly_revenue * lifetime_months if avg_monthly_revenue else None
    cac = safe_div(spend, won)
    return MarketingKpis(
        spend=spend, leads=leads, trials=trials, won=won,
        cpl=safe_div(spend, leads), cost_per_trial=safe_div(spend, trials), cac=cac,
        lead_to_trial=safe_div(trials, leads), trial_to_won=safe_div(won, trials),
        lead_to_won=safe_div(won, leads),
        realized_revenue=realized_revenue, roas=safe_div(realized_revenue, spend),
        ltv=ltv, ltv_cac=safe_div(ltv, cac),
        projected_roi=safe_div(won * ltv - spend, spend) if ltv is not None and spend else None,
    )


def lifetime_months(tenures_of_left: list[float], fallback: float, min_sample: int = 20) -> float:
    """Ortalama üyelik süresi. Küçük örneklemde (n<20) kulüp varsayımına geri düşer,
    çünkü ilk ayrılanlar erken ayrılanlardır ve ortalamayı aşağı yanlılar."""
    if len(tenures_of_left) < min_sample:
        return fallback
    return statistics.median(tenures_of_left)


# ── Performans ────────────────────────────────────────────────────────────────

class ChangeVerdict(StrEnum):
    IMPROVED = "IMPROVED"
    DECLINED = "DECLINED"
    TRIVIAL = "TRIVIAL"  # SWC altında: gerçek değişim değil
    UNCLEAR = "UNCLEAR"  # SWC üstü ama ölçüm hatası içinde


def swc(values: list[float]) -> float | None:
    """Smallest worthwhile change = 0.2 × gruplar arası standart sapma."""
    if len(values) < 3:
        return None
    return 0.2 * statistics.stdev(values)


def classify_change(delta: float, swc_value: float | None, typical_error: float | None,
                    higher_is_better: bool) -> ChangeVerdict:
    if swc_value is None:
        return ChangeVerdict.UNCLEAR
    signed = delta if higher_is_better else -delta
    if abs(delta) < swc_value:
        return ChangeVerdict.TRIVIAL
    # İki ölçümün farkının gürültüsü ≈ √2 × TE. Değişim bundan küçükse kesin değil.
    if typical_error and abs(delta) < 1.414 * typical_error:
        return ChangeVerdict.UNCLEAR
    return ChangeVerdict.IMPROVED if signed > 0 else ChangeVerdict.DECLINED


def zscore(value: float, peers: list[float], higher_is_better: bool) -> float | None:
    """Yaş grubu içi z-skoru; yön düzeltilmiş (pozitif = iyi)."""
    if len(peers) < 3:
        return None
    sd = statistics.stdev(peers)
    if sd == 0:
        return 0.0
    z = (value - statistics.mean(peers)) / sd
    return z if higher_is_better else -z


def maturity_offset(gender: str, age_years: float, height_cm: float | None,
                    sitting_height_cm: float | None) -> float | None:
    """PHV'ye kalan (negatif) / PHV'den geçen (pozitif) yıl. Moore et al. 2015.

    Erkek: −8.128741 + 0.0070346 × (yaş × oturma boyu)
    Kız:   −7.709133 + 0.0042232 × (yaş × boy)
    Geçerlilik: ~8-16 yaş; ±0.5-1 yıl hata payıyla yorumlanmalı (bireysel karar değil,
    biyolojik olgunluğa göre gruplama / yük ayarı için).
    """
    if gender == "MALE":
        if sitting_height_cm is None:
            return None
        return -8.128741 + 0.0070346 * (age_years * sitting_height_cm)
    if height_cm is None:
        return None
    return -7.709133 + 0.0042232 * (age_years * height_cm)


def maturity_status(offset: float | None) -> str | None:
    if offset is None:
        return None
    if offset < -1:
        return "PRE_PHV"
    if offset <= 1:
        return "CIRCA_PHV"  # büyüme atağı: sakatlık riski ↑, koordinasyon geçici ↓
    return "POST_PHV"


def session_load(rpe: int | None, minutes: int | None) -> int | None:
    """sRPE yükü (arbitrary units)."""
    if rpe is None or minutes is None:
        return None
    return rpe * minutes


@dataclass(frozen=True)
class WeeklyLoad:
    total: int
    monotony: float | None
    strain: float | None


def weekly_load(daily_loads: list[int]) -> WeeklyLoad:
    """daily_loads: 7 günlük yük (dinlenme günleri 0). Monotoni > 2 → aşırı tekdüze."""
    days = (daily_loads + [0] * 7)[:7]
    total = sum(days)
    sd = statistics.pstdev(days)
    monotony = statistics.mean(days) / sd if sd > 0 else None
    return WeeklyLoad(total, monotony, total * monotony if monotony is not None else None)


def shooting_efficiency(pts: int, fgm: int, fga: int, tpm: int, fta: int) -> dict[str, float | None]:
    return {
        "efg": safe_div(fgm + 0.5 * tpm, fga),
        "ts": safe_div(pts, 2 * (fga + 0.44 * fta)),
    }


def birth_quarter(month: int) -> int:
    """Göreceli yaş etkisi (RAE) analizi için doğum çeyreği."""
    return (month - 1) // 3 + 1
