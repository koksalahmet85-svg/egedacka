from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def D(value: object) -> Decimal:
    """Her şeyi güvenle Decimal'e çevirir. float girişi string üzerinden geçer."""
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(str(value))


def money(value: object) -> Decimal:
    """Kuruşa yuvarla (bankacı değil, ticari yuvarlama: 0.005 → 0.01)."""
    return D(value).quantize(CENT, rounding=ROUND_HALF_UP)
