"""Sporcu performans metrikleri.

Kaynaklar:
  - sRPE yükü: Foster C. ve ark. (2001), J Strength Cond Res 15(1):109-115.
  - SWC = 0.2 × sporcular arası SD; anlamlı değişim için |Δ| > SWC ve |Δ| > TE:
    Hopkins W.G. (2000), Sports Med 30(1):1-15.
  - Olgunlaşma ofseti (PHV'ye kalan yıl): Moore S.A. ve ark. (2015),
    Med Sci Sports Exerc 47(8):1755-1764. ±1 yıl hata payı vardır; yalnızca
    gruplama (bio-banding) için kullanılmalı, bireysel kehanet için değil.
  - PIR: EuroLeague Performance Index Rating.
  - ACWR bilinçli olarak kullanılmıyor: Impellizzeri F.M. ve ark. (2020),
    Int J Sports Physiol Perform 15(6):907-913 — sakatlık tahmin geçerliliği zayıf.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class BoxScore:
    seconds: int = 0
    points: int = 0
    fgm2: int = 0
    fga2: int = 0
    fgm3: int = 0
    fga3: int = 0
    ftm: int = 0
    fta: int = 0
    oreb: int = 0
    dreb: int = 0
    ast: int = 0
    stl: int = 0
    blk: int = 0
    tov: int = 0
    pf: int = 0
    fouls_drawn: int = 0
    blocks_against: int = 0

    @property
    def rebounds(self) -> int:
        return self.oreb + self.dreb


def pir(b: BoxScore) -> int:
    missed_fg = (b.fga2 - b.fgm2) + (b.fga3 - b.fgm3)
    missed_ft = b.fta - b.ftm
    return (
        b.points
        + b.rebounds
        + b.ast
        + b.stl
        + b.blk
        + b.fouls_drawn
        - missed_fg
        - missed_ft
        - b.tov
        - b.pf
        - b.blocks_against
    )


def efg_pct(b: BoxScore) -> float | None:
    fga = b.fga2 + b.fga3
    if not fga:
        return None
    return round((b.fgm2 + 1.5 * b.fgm3) / fga * 100, 1)


def ts_pct(b: BoxScore) -> float | None:
    tsa = (b.fga2 + b.fga3) + 0.44 * b.fta
    if not tsa:
        return None
    return round(b.points / (2 * tsa) * 100, 1)


def attendance_rate(attended: int, total: int) -> float:
    return 0.0 if total == 0 else round(attended / total * 100, 1)


def srpe_load(rpe: int, minutes: int) -> int:
    if not 0 <= rpe <= 10:
        raise ValueError("RPE 0-10 (CR-10) aralığında olmalı")
    return rpe * minutes


def swc(group_values: list[float], factor: float = 0.2) -> float | None:
    """Smallest worthwhile change: grup içi SD × 0.2 (en az 2 değer)."""
    if len(group_values) < 2:
        return None
    return round(statistics.stdev(group_values) * factor, 3)


def change_verdict(
    previous: float,
    current: float,
    higher_is_better: bool,
    swc_value: float | None,
    typical_error: float | None,
) -> str:
    """'improved' | 'declined' | 'trivial' | 'unclear'.

    Δ hem SWC'yi hem tipik hatayı aşmıyorsa değişim gürültüden ayırt edilemez.
    """
    delta = current - previous
    if swc_value is None and typical_error is None:
        return "unclear"
    threshold = max(swc_value or 0.0, typical_error or 0.0)
    if abs(delta) <= threshold:
        return "trivial"
    good = delta > 0 if higher_is_better else delta < 0
    return "improved" if good else "declined"


def decimal_age(birth: date, on: date) -> float:
    return round((on - birth).days / 365.25, 2)


def maturity_offset(gender: str, age: float, height_cm: float, sitting_height_cm: float | None = None) -> float:
    """Moore 2015. Erkek: oturma boyu gerekir; kız: yalnızca boy."""
    if gender == "MALE":
        if sitting_height_cm is None:
            raise ValueError("erkekler için oturma boyu gerekli")
        return round(-8.128741 + 0.0070346 * (age * sitting_height_cm), 2)
    if gender == "FEMALE":
        return round(-7.709133 + 0.0042232 * (age * height_cm), 2)
    raise ValueError("gender MALE veya FEMALE olmalı")


def maturity_band(offset: float) -> str:
    """Bio-banding grubu: PHV öncesi / çevresi / sonrası."""
    if offset < -1.0:
        return "PRE_PHV"
    if offset <= 1.0:
        return "CIRCA_PHV"
    return "POST_PHV"
