"""Tahsilat defteri değişiklik denetimi: iki sürüm arasında kayıt bazlı fark.

Satır numarası değişebilir (araya satır eklenir/silinir), bu yüzden eşleştirme
iki aşamalıdır:
  1) Aynı sayfa + aynı satır + aynı içerik → değişmemiş.
  2) Kalanlar, sayfa içinde içerik anahtarıyla (tarih, oyuncu, dönem, tutar) eşleşirse
     → yalnız yeri değişmiş (kaydırılmış) satır, finansal fark yok.
  3) Aynı sayfa + aynı satır + aynı oyuncu ama farklı tutar/dönem → DEĞİŞEN.
  4) Kalan yeni satırlar → EKLENEN, kalan eski satırlar → SİLİNEN.
Toplam değişmese bile birbirini dengeleyen ekleme/silmeler ayrıca listelenir.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal

from .ledger_import import LedgerRecord, ParseResult

FIELDS = ("paid_on", "player_name", "group", "period_label", "amount", "dues_amount", "textile_amount",
          "channel_raw", "cancelled")


def _content(r: LedgerRecord) -> tuple:
    return tuple(getattr(r, f) for f in FIELDS)


@dataclass
class Change:
    kind: str  # ADDED | REMOVED | CHANGED | MOVED
    sheet: str
    old_row: int | None
    new_row: int | None
    player_name: str
    old: dict | None
    new: dict | None
    amount_delta: Decimal


@dataclass
class DiffResult:
    changes: list[Change] = field(default_factory=list)
    sheets_added: list[str] = field(default_factory=list)
    sheets_removed: list[str] = field(default_factory=list)

    def net_delta(self) -> Decimal:
        return sum((c.amount_delta for c in self.changes), Decimal(0))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = defaultdict(int)
        for c in self.changes:
            out[c.kind] += 1
        return dict(out)


def _view(r: LedgerRecord) -> dict:
    return {f: (str(getattr(r, f)) if not isinstance(getattr(r, f), (bool, str)) else getattr(r, f)) for f in FIELDS} | {
        "kind": r.kind, "row": r.source_row}


def _amt(r: LedgerRecord) -> Decimal:
    return Decimal(0) if r.cancelled else r.amount


def diff(old: ParseResult, new: ParseResult) -> DiffResult:
    res = DiffResult(sheets_added=[s for s in new.sheets if s not in old.sheets],
                     sheets_removed=[s for s in old.sheets if s not in new.sheets])
    for sheet in sorted(set(old.sheets) | set(new.sheets), key=lambda s: (new.sheets + old.sheets).index(s)):
        o = {r.source_row: r for r in old.records if r.sheet == sheet}
        n = {r.source_row: r for r in new.records if r.sheet == sheet}
        # 1) aynı satır, aynı içerik
        same = {row for row in o.keys() & n.keys() if _content(o[row]) == _content(n[row])}
        o_left = {k: v for k, v in o.items() if k not in same}
        n_left = {k: v for k, v in n.items() if k not in same}
        # 2) yer değiştirmiş satırlar (içerik birebir aynı)
        by_content: dict[tuple, list[int]] = defaultdict(list)
        for row, r in sorted(o_left.items()):
            by_content[_content(r)].append(row)
        for row, r in sorted(n_left.items()):
            bucket = by_content.get(_content(r))
            if bucket:
                orow = bucket.pop(0)
                o_left.pop(orow)
                n_left.pop(row)
                res.changes.append(Change("MOVED", sheet, orow, row, r.player_name, None, None, Decimal(0)))
        # 3) aynı satır, aynı oyuncu, farklı içerik → değişen
        for row in sorted(o_left.keys() & n_left.keys()):
            if o_left[row].player_key == n_left[row].player_key:
                a, b = o_left.pop(row), n_left.pop(row)
                res.changes.append(Change("CHANGED", sheet, row, row, b.player_name, _view(a), _view(b),
                                          _amt(b) - _amt(a)))
        # 4) kalanlar
        for row, r in sorted(n_left.items()):
            res.changes.append(Change("ADDED", sheet, None, row, r.player_name, None, _view(r), _amt(r)))
        for row, r in sorted(o_left.items()):
            res.changes.append(Change("REMOVED", sheet, row, None, r.player_name, _view(r), None, -_amt(r)))
    return res
