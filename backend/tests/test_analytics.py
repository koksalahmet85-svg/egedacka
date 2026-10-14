from datetime import date
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.services import analytics as an
from app.services.scheduling import plan_occurrences, week_start


def test_invoice_amounts_vat_inclusive_and_sibling_discount():
    first = an.invoice_amounts(Decimal("4500"), Decimal("20"), Decimal("0"), Decimal("10"), 1)
    assert first.total == Decimal("4500.00")
    assert first.subtotal + first.vat == first.total
    assert first.subtotal == Decimal("3750.00")

    second = an.invoice_amounts(Decimal("4500"), Decimal("20"), Decimal("0"), Decimal("10"), 2)
    assert second.total == Decimal("4050.00")
    assert second.discount == Decimal("450.00")


def test_discounts_compound_not_add():
    # %50 burs + %10 kardeş = %55 (çarpımsal), %60 değil.
    amt = an.invoice_amounts(Decimal("1000"), Decimal("20"), Decimal("50"), Decimal("10"), 3)
    assert amt.total == Decimal("450.00")


def test_marketing_kpis():
    k = an.marketing_kpis(spend=10000, leads=100, trials=40, won=20, realized_revenue=30000,
                          avg_monthly_revenue=4000, lifetime_months=18)
    assert k.cpl == 100 and k.cac == 500
    assert k.lead_to_trial == 0.4 and k.trial_to_won == 0.5
    assert k.roas == 3
    assert k.ltv == 72000 and k.ltv_cac == 144
    assert k.projected_roi == pytest.approx((20 * 72000 - 10000) / 10000)


def test_marketing_kpis_zero_spend_is_not_division_error():
    k = an.marketing_kpis(0, 10, 0, 0, 0, None, 18)
    assert k.cac is None and k.roas is None and k.projected_roi is None


def test_lifetime_falls_back_on_small_sample():
    assert an.lifetime_months([3, 4, 5], fallback=18) == 18
    assert an.lifetime_months([12.0] * 25, fallback=18) == 12


def test_swc_and_change_classification():
    peers = [30.0, 32.0, 34.0, 36.0, 38.0]  # sd ≈ 3.16 → SWC ≈ 0.63
    s = an.swc(peers)
    assert s == pytest.approx(0.632, abs=1e-3)
    assert an.classify_change(0.3, s, None, True) == an.ChangeVerdict.TRIVIAL
    assert an.classify_change(2.0, s, 1.5, True) == an.ChangeVerdict.UNCLEAR  # < √2·TE ≈ 2.12
    assert an.classify_change(3.0, s, 1.5, True) == an.ChangeVerdict.IMPROVED
    # Sprint: süre düşerse gelişim.
    assert an.classify_change(-0.2, 0.05, 0.04, False) == an.ChangeVerdict.IMPROVED
    assert an.swc([1.0, 2.0]) is None


def test_zscore_direction():
    peers = [3.0, 3.1, 3.2, 3.3, 3.4]
    assert an.zscore(3.0, peers, higher_is_better=False) > 0  # en hızlı sprint pozitif
    assert an.zscore(3.0, [3.0, 3.0, 3.0], True) == 0.0


def test_maturity_offset_moore_2015():
    # 14 yaş erkek, oturma boyu 85 cm → −8.128741 + 0.0070346·(14·85) ≈ 0.243
    off = an.maturity_offset("MALE", 14.0, 170, 85)
    assert off == pytest.approx(0.2424, abs=1e-3)
    assert an.maturity_status(off) == "CIRCA_PHV"
    assert an.maturity_offset("MALE", 14.0, 170, None) is None
    assert an.maturity_status(an.maturity_offset("FEMALE", 10.0, 140, None)) == "PRE_PHV"


def test_weekly_load_monotony():
    w = an.weekly_load([500, 0, 500, 0, 500, 0, 0])
    assert w.total == 1500
    assert w.monotony == pytest.approx(214.2857 / 247.4358, rel=1e-3)
    assert an.weekly_load([0] * 7).monotony is None


def test_shooting_efficiency():
    e = an.shooting_efficiency(pts=20, fgm=8, fga=16, tpm=2, fta=4)
    assert e["efg"] == pytest.approx(0.5625)
    assert e["ts"] == pytest.approx(20 / (2 * (16 + 1.76)))


def test_plan_occurrences_local_time_and_validity():
    tz = ZoneInfo("Europe/Istanbul")
    monday = week_start(date(2026, 10, 14))
    assert monday == date(2026, 10, 12)
    plans = [
        {"id": 1, "team_id": 1, "coach_id": 1, "facility_id": 1, "weekday": 3, "start_time": "17:30",
         "duration_min": 90, "valid_from": date(2026, 9, 1), "valid_to": None, "focus": None},
        {"id": 2, "team_id": 1, "coach_id": 1, "facility_id": 1, "weekday": 1, "start_time": "17:30",
         "duration_min": 90, "valid_from": date(2026, 10, 13), "valid_to": None, "focus": None},  # henüz geçerli değil
    ]
    occ = plan_occurrences(plans, monday, tz)
    assert len(occ) == 1
    assert occ[0].starts_at.isoformat() == "2026-10-14T17:30:00+03:00"
    assert (occ[0].ends_at - occ[0].starts_at).seconds == 90 * 60
