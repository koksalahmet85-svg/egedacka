"""Maaş hesabı.

Not: SGK primi, gelir vergisi dilimleri ve damga vergisi her yıl değişir ve mali
müşavirin bordro yazılımında hesaplanır. Bu modül brüt hakedişi (sabit + puantaj +
seans + prim) üretir; kesintiler dışarıdan `deductions` olarak girilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from .money import ZERO, D, money


@dataclass(frozen=True)
class PayInput:
    pay_type: str  # MONTHLY | HOURLY | PER_SESSION | MIXED
    base_salary: Decimal = ZERO
    hourly_rate: Decimal | None = None
    session_rate: Decimal | None = None
    worked_minutes: int = 0
    session_count: int = 0
    bonus: Decimal = ZERO
    deductions: Decimal = ZERO


@dataclass(frozen=True)
class PayResult:
    base_amount: Decimal
    variable_amount: Decimal
    gross: Decimal
    net: Decimal
    lines: list[dict] = field(default_factory=list)


def compute_payslip(p: PayInput) -> PayResult:
    lines: list[dict] = []
    base = ZERO
    variable = ZERO

    if p.pay_type in ("MONTHLY", "MIXED"):
        base = money(p.base_salary)
        lines.append({"label": "Sabit maaş", "amount": str(base)})

    if p.pay_type == "HOURLY":
        if p.hourly_rate is None:
            raise ValueError("HOURLY personel için hourly_rate zorunlu")
        hours = D(p.worked_minutes) / 60
        variable = money(hours * D(p.hourly_rate))
        lines.append({"label": f"Puantaj {hours:.2f} saat", "amount": str(variable)})

    if p.pay_type in ("PER_SESSION", "MIXED"):
        if p.session_rate is None:
            raise ValueError(f"{p.pay_type} personel için session_rate zorunlu")
        variable = money(D(p.session_count) * D(p.session_rate))
        lines.append({"label": f"{p.session_count} antrenman", "amount": str(variable)})

    bonus = money(p.bonus)
    if bonus:
        lines.append({"label": "Prim", "amount": str(bonus)})

    gross = base + variable + bonus
    deductions = money(p.deductions)
    if deductions:
        lines.append({"label": "Kesintiler", "amount": str(-deductions)})
    net = gross - deductions
    if net < ZERO:
        raise ValueError("kesintiler brüt tutarı aşamaz")
    return PayResult(base_amount=base, variable_amount=variable, gross=gross, net=net, lines=lines)
