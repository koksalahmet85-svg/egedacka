from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.domain.billing import (
    OpenCharge,
    allocate_payment,
    charge_status,
    compute_charge_amounts,
    due_date_for,
    prorated_first_month,
    reminder_level,
    sibling_discount_pct,
)
from app.domain.marketing import FunnelCounts, RoiInput, expected_tenure_months, funnel_rates, roi_metrics
from app.domain.payroll import PayInput, compute_payslip
from app.domain.performance import (
    BoxScore,
    change_verdict,
    efg_pct,
    maturity_band,
    maturity_offset,
    pir,
    srpe_load,
    swc,
    ts_pct,
)
from app.domain.scheduling import Booked, Slot, expand_week, find_conflicts

# ── Finans ──


def test_charge_amounts_with_discount():
    a = compute_charge_amounts("2500", 10)
    assert (a.gross, a.discount, a.net) == (Decimal("2500.00"), Decimal("250.00"), Decimal("2250.00"))


def test_charge_amounts_rejects_bad_pct():
    with pytest.raises(ValueError):
        compute_charge_amounts(100, 120)


def test_sibling_policy():
    assert [sibling_discount_pct(i) for i in (1, 2, 3, 4)] == [0, 10, 15, 15]


def test_due_date_clamps_short_months():
    assert due_date_for(date(2026, 2, 1), 31) == date(2026, 2, 28)
    assert due_date_for(date(2026, 3, 1), 5) == date(2026, 3, 5)


def test_proration():
    # 16 Eylül başlangıç: 30 günün 15'i
    assert prorated_first_month(Decimal("3000"), date(2026, 9, 16)) == Decimal("1500.00")


def test_fifo_allocation_and_credit():
    charges = [
        OpenCharge("b", date(2026, 10, 5), Decimal("2000")),
        OpenCharge("a", date(2026, 9, 5), Decimal("1500")),
    ]
    allocs, left = allocate_payment("4000", charges)
    assert [(x.charge_id, x.amount) for x in allocs] == [("a", Decimal("1500.00")), ("b", Decimal("2000"))]
    assert left == Decimal("500.00")


def test_partial_allocation():
    allocs, left = allocate_payment("1000", [OpenCharge("a", date(2026, 9, 5), Decimal("1500"))])
    assert allocs[0].amount == Decimal("1000.00") and left == 0


def test_charge_status_transitions():
    due = date(2026, 10, 5)
    assert charge_status(100, 0, due, date(2026, 10, 1)) == "PENDING"
    assert charge_status(100, 40, due, date(2026, 10, 1)) == "PARTIALLY_PAID"
    assert charge_status(100, 40, due, date(2026, 10, 6)) == "OVERDUE"
    assert charge_status(100, 100, due, date(2026, 12, 1)) == "PAID"


@pytest.mark.parametrize("late,level", [(0, 0), (2, 0), (3, 1), (9, 1), (10, 2), (19, 2), (20, 3), (90, 3)])
def test_reminder_levels(late, level):
    due = date(2026, 10, 1)
    assert reminder_level(due, date.fromordinal(due.toordinal() + late)) == level


# ── Bordro ──


def test_payroll_mixed():
    r = compute_payslip(
        PayInput(
            "MIXED",
            base_salary=Decimal("20000"),
            session_rate=Decimal("400"),
            session_count=12,
            bonus=Decimal("1000"),
            deductions=Decimal("3000"),
        )
    )
    assert r.gross == Decimal("25800.00") and r.net == Decimal("22800.00")


def test_payroll_hourly():
    r = compute_payslip(PayInput("HOURLY", hourly_rate=Decimal("300"), worked_minutes=90))
    assert r.gross == Decimal("450.00")


def test_payroll_requires_rate():
    with pytest.raises(ValueError):
        compute_payslip(PayInput("PER_SESSION", session_count=3))


# ── Pazarlama ──


def test_funnel_rates():
    r = funnel_rates(FunnelCounts(200, 160, 80, 60, 30))
    assert r == {
        "contactRate": 80.0,
        "trialBookRate": 50.0,
        "trialShowRate": 75.0,
        "trialToMemberRate": 50.0,
        "leadToMemberRate": 15.0,
    }


def test_roi_metrics():
    m = roi_metrics(
        RoiInput(
            spend=Decimal("30000"),
            leads=200,
            won=30,
            attributed_revenue=Decimal("75000"),
            avg_monthly_fee=Decimal("2500"),
            expected_tenure_months=Decimal("14"),
        )
    )
    assert m["cpl"] == Decimal("150.00")
    assert m["cac"] == Decimal("1000.00")
    assert m["roas"] == 2.5 and m["roi"] == 150.0
    assert m["ltv"] == Decimal("35000.00") and m["ltvToCac"] == 35.0
    assert m["paybackMonths"] == 0.4


def test_roi_zero_spend_is_none_not_crash():
    m = roi_metrics(RoiInput(Decimal(0), 0, 0, Decimal(0), Decimal(0), Decimal(12)))
    assert m["roi"] is None and m["cac"] is None and m["paybackMonths"] is None


def test_tenure():
    assert expected_tenure_months(0.05) == Decimal("20.0")
    assert expected_tenure_months(0.0) == Decimal("36.0")
    assert expected_tenure_months(0.01) == Decimal("36.0")  # tavan


# ── Performans ──


def test_pir_and_shooting():
    b = BoxScore(
        points=18,
        fgm2=5,
        fga2=9,
        fgm3=2,
        fga3=6,
        ftm=2,
        fta=4,
        oreb=2,
        dreb=5,
        ast=4,
        stl=2,
        blk=1,
        tov=3,
        pf=2,
        fouls_drawn=4,
        blocks_against=1,
    )
    # 18+7+4+2+1+4 − (4+4) − 2 − 3 − 2 − 1 = 20
    assert pir(b) == 20
    assert efg_pct(b) == 53.3
    assert ts_pct(b) == 53.7  # 18 / (2 × (15 + 0.44×4))


def test_srpe():
    assert srpe_load(6, 90) == 540
    with pytest.raises(ValueError):
        srpe_load(11, 60)


def test_swc_and_verdicts():
    s = swc([30.0, 34.0, 38.0, 42.0])  # SD ≈ 5.164 → 1.033
    assert s == pytest.approx(1.033, abs=1e-3)
    assert change_verdict(35.0, 35.8, True, s, 0.6) == "trivial"
    assert change_verdict(35.0, 37.0, True, s, 0.6) == "improved"
    # Sprint: düşük daha iyi
    assert change_verdict(3.40, 3.20, False, 0.05, 0.04) == "improved"
    assert change_verdict(3.40, 3.60, False, 0.05, 0.04) == "declined"
    assert change_verdict(1, 2, True, None, None) == "unclear"


def test_maturity_offset_moore_2015():
    boy = maturity_offset("MALE", 13.0, 160.0, sitting_height_cm=82.0)
    assert boy == pytest.approx(-0.63, abs=0.01)
    assert maturity_band(boy) == "CIRCA_PHV"
    girl = maturity_offset("FEMALE", 11.0, 145.0)
    assert girl == pytest.approx(-0.97, abs=0.01)
    with pytest.raises(ValueError):
        maturity_offset("MALE", 13.0, 160.0)


# ── Çizelgeleme ──


def _slot(i, team, court, coach, wd, s, e):
    return Slot(i, team, court, coach, wd, s, e, date(2026, 9, 1))


def test_expand_week_converts_istanbul_to_utc():
    drafts = expand_week([_slot("s1", "t1", "c1", "k1", 1, "18:00", "19:30")], date(2026, 10, 12))
    assert drafts[0].starts_at == datetime(2026, 10, 13, 15, 0, tzinfo=UTC)  # UTC+3
    assert drafts[0].ends_at == datetime(2026, 10, 13, 16, 30, tzinfo=UTC)


def test_expand_week_requires_monday():
    with pytest.raises(ValueError):
        expand_week([], date(2026, 10, 14))


def test_conflicts_court_and_coach_and_back_to_back():
    ws = date(2026, 10, 12)
    drafts = expand_week(
        [
            _slot("s1", "t1", "c1", "k1", 0, "18:00", "19:30"),
            _slot("s2", "t2", "c1", "k2", 0, "19:00", "20:00"),  # saha çakışır
            _slot("s3", "t3", "c2", "k1", 0, "19:30", "21:00"),  # arka arkaya: çakışmaz
        ],
        ws,
    )
    conf = find_conflicts(drafts, [])
    assert [(c.kind, c.draft.team_id) for c in conf] == [("court", "t2")]

    existing = [Booked("x", "c9", "k2", drafts[1].starts_at, drafts[1].ends_at)]
    kinds = {c.kind for c in find_conflicts(drafts, existing)}
    assert kinds == {"court", "coach"}
