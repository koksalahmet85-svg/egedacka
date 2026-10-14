"""Aidat tahakkuku, indirim, ödeme dağıtımı ve gecikme kademeleri."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .money import ZERO, D, money

# Kardeş indirimi politikası: kayıt sırasına göre (en büyük ücret tam fiyat).
# Kulüp yönetimi değiştirirse yalnızca bu tablo güncellenir.
SIBLING_DISCOUNT_BY_ORDER: dict[int, Decimal] = {1: D(0), 2: D(10), 3: D(15)}
SIBLING_DISCOUNT_MAX = D(15)

# Gecikme kademeleri: vadeden sonraki gün sayısı → hatırlatma seviyesi.
#   L1 (D+3)  : nazik WhatsApp hatırlatma
#   L2 (D+10) : ikinci hatırlatma + ödeme linki
#   L3 (D+20) : yöneticiye eskalasyon, veliyle birebir görüşme
REMINDER_THRESHOLDS: tuple[tuple[int, int], ...] = ((20, 3), (10, 2), (3, 1))


@dataclass(frozen=True)
class ChargeAmounts:
    gross: Decimal
    discount: Decimal
    net: Decimal


def sibling_discount_pct(order: int) -> Decimal:
    """order: aynı velinin aktif çocukları arasında 1'den başlayan sıra."""
    if order < 1:
        raise ValueError("order >= 1 olmalı")
    return SIBLING_DISCOUNT_BY_ORDER.get(order, SIBLING_DISCOUNT_MAX)


def compute_charge_amounts(list_price: object, discount_pct: object) -> ChargeAmounts:
    gross = money(list_price)
    pct = D(discount_pct)
    if not (D(0) <= pct <= D(100)):
        raise ValueError("indirim yüzdesi 0-100 aralığında olmalı")
    discount = money(gross * pct / 100)
    return ChargeAmounts(gross=gross, discount=discount, net=gross - discount)


def first_of_month(d: date) -> date:
    return d.replace(day=1)


def due_date_for(period: date, due_day: int) -> date:
    """Ayın due_day'i; kısa aylarda ayın son gününe sabitlenir (ör. 31 → 28 Şubat)."""
    last = calendar.monthrange(period.year, period.month)[1]
    return period.replace(day=min(max(due_day, 1), last))


def prorated_first_month(net: Decimal, start: date) -> Decimal:
    """Ay ortasında başlayan sporcu için ilk ay kıstelyevm (gün bazlı)."""
    days_in_month = calendar.monthrange(start.year, start.month)[1]
    remaining = days_in_month - start.day + 1
    return money(D(net) * remaining / days_in_month)


@dataclass(frozen=True)
class OpenCharge:
    id: str
    due_date: date
    outstanding: Decimal


@dataclass(frozen=True)
class Allocation:
    charge_id: str
    amount: Decimal


def allocate_payment(amount: object, open_charges: list[OpenCharge]) -> tuple[list[Allocation], Decimal]:
    """Ödemeyi en eski vadeli borçtan başlayarak kapatır (FIFO).

    Döner: (dağıtımlar, artan_tutar). Artan tutar velinin alacak bakiyesidir.
    """
    remaining = money(amount)
    if remaining <= ZERO:
        raise ValueError("ödeme tutarı pozitif olmalı")
    allocations: list[Allocation] = []
    for ch in sorted(open_charges, key=lambda c: (c.due_date, c.id)):
        if remaining <= ZERO:
            break
        if ch.outstanding <= ZERO:
            continue
        take = min(remaining, ch.outstanding)
        allocations.append(Allocation(charge_id=ch.id, amount=take))
        remaining -= take
    return allocations, remaining


def charge_status(net: object, paid: object, due: date, today: date) -> str:
    net_d, paid_d = money(net), money(paid)
    if paid_d >= net_d:
        return "PAID"
    if today > due:
        return "OVERDUE"
    if paid_d > ZERO:
        return "PARTIALLY_PAID"
    return "PENDING"


def reminder_level(due: date, today: date) -> int:
    days_late = (today - due).days
    for threshold, level in REMINDER_THRESHOLDS:
        if days_late >= threshold:
            return level
    return 0
