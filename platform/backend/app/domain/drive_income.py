"""Drive'daki "GENEL ÖDEME TABLOSU" sayfalarını okuyup gelir verisine çeviren saf mantık.

Tablo yapısı (kulübün mevcut düzeni, değiştirmeden okunur):
  * Bir başlık satırında "AD SOYAD" ve sezon ayları (TEMMUZ → AĞUSTOS, 14 ay) bulunur.
  * Her satır bir sporcudur; ay hücresinde ya tutar ya da durum yazar:
      45.000,00 TRY / ₺19.800 / 8100   → ödeme (PAID)
      SEZONLUK                          → sezonluk ödemeyle kapalı
      BURSLU, %50 BURSLU                → burs
      AYLIK                             → aylık sporcunun başlamadan önceki yer tutucusu
      boş, ".", "-"                     → kayıt yok
      diğer metin (GELMEDİ …)            → not
  * Sütun sırası sayfadan sayfaya değişir (Spor Okulu ≠ Altyapı); başlıklar adla bulunur.

Not: Ay sütunu, ödemenin YAPILDIĞI ayı değil ait olduğu AİDAT AYINI gösterir
("Ekim ayında Eylül aidatını ödedi" notları). Aylık toplamlar bu nedenle aidat-ayı bazlıdır.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation

from .money import money

MONTHS_TR = [
    "OCAK",
    "ŞUBAT",
    "MART",
    "NİSAN",
    "MAYIS",
    "HAZİRAN",
    "TEMMUZ",
    "AĞUSTOS",
    "EYLÜL",
    "EKİM",
    "KASIM",
    "ARALIK",
]
_MONTH_INDEX = {m: i + 1 for i, m in enumerate(MONTHS_TR)}

PROGRAMS = ("SPOR_OKULU", "ALTYAPI", "MASA_TENISI", "DIGER")

# Hücre durumları
PAID, SEASON, SCHOLARSHIP, PLACEHOLDER, EMPTY, NOTE = (
    "PAID",
    "SEASON_COVERED",
    "SCHOLARSHIP",
    "NOT_STARTED",
    "EMPTY",
    "NOTE",
)

# Satır (ödeme türü) sınıfları
MONTHLY, SEASONAL, FULL_SCHOLAR, PARTIAL_SCHOLAR, PROSPECT, UNKNOWN = (
    "AYLIK",
    "SEZONLUK",
    "BURSLU",
    "KISMI_BURSLU",
    "ADAY",
    "BELIRSIZ",
)

LEFT_MARKERS = ("BIRAKTI", "AYRILDI", "GELMEYECEK", "KAYIT SİLİNDİ")
PROSPECT_MARKERS = ("DENEME", "ARANACAK", "İLETİŞİM YOK", "ILETISIM YOK", "BİLGİ ALDI")


def norm(text: object) -> str:
    """Türkçe büyük harf + boşluk sadeleştirme. 'ad - soyad ' → 'AD - SOYAD'."""
    s = "" if text is None else str(text)
    s = s.replace("i", "İ").replace("ı", "I").upper()
    return re.sub(r"\s+", " ", s).strip()


def _key(text: object) -> str:
    """Başlık eşleme anahtarı: harf dışı her şey atılır. 'AD- SOYAD' → 'ADSOYAD'."""
    return re.sub(r"[^A-ZÇĞİÖŞÜ]", "", norm(text))


# ── Tutar ayrıştırma ─────────────────────────────────────────────────────────

_THOUSANDS_ONLY = re.compile(r"^\d{1,3}(\.\d{3})+$")


def parse_amount(value: object) -> Decimal | None:
    """'45.000,00 TRY', '₺19.800', '650,00', '2.600', 8100.0 → Decimal. Tutar değilse None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | Decimal):
        return money(value) if value > 0 else None
    s = norm(value).replace("TRY", "").replace("TL", "").replace("₺", "").replace(" ", "")
    if not s or not re.fullmatch(r"[\d.,]+", s) or not re.search(r"\d", s):
        return None
    try:
        if "," in s:  # Türkçe biçim: binlik nokta, ondalık virgül
            d = Decimal(s.replace(".", "").replace(",", "."))
        elif _THOUSANDS_ONLY.match(s):  # 19.800 → 19800
            d = Decimal(s.replace(".", ""))
        else:
            d = Decimal(s)
    except InvalidOperation:
        return None
    return money(d) if d > 0 else None


def classify_cell(value: object) -> tuple[str, Decimal | None]:
    amount = parse_amount(value)
    if amount is not None:
        return PAID, amount
    s = norm(value)
    if s in ("", ".", "-", "—", "0", "₺0", "₺0,00"):
        return EMPTY, None
    if "BURSLU" in s:
        return SCHOLARSHIP, None
    if s == "SEZONLUK" or s.startswith("SEZONLUK"):
        return SEASON, None
    if s == "AYLIK" or s == "AYLIKI":
        return PLACEHOLDER, None
    return NOTE, None


# ── Sayfa yapısı ─────────────────────────────────────────────────────────────

HEADER_ALIASES = {
    "name": ("ADSOYAD",),
    "payment_type": ("ÖDEMETÜRÜ", "ÖDEMETERCİH", "ÖDEMETERCIH"),
    "no": ("NO",),
    "team": ("TAKIMİSMİ", "TAKIM", "GRUP"),
    "coach": ("KOÇ",),
    "birth_year": ("DOĞUMYILI",),
    "textile_fee": ("ÜCRET",),
    "note": ("AÇIKLAMA", "NOT"),
}


@dataclass(frozen=True)
class SheetLayout:
    header_row: int  # 0-tabanlı
    columns: dict[str, int]
    month_columns: list[tuple[int, date]]  # (sütun, ayın 1'i)


def detect_season(*texts: str) -> int | None:
    """'26-27', '2026-2027', '2025- 2026' → başlangıç yılı (2026, 2025)."""
    for t in texts:
        m = re.search(r"(?<!\d)(\d{2}|\d{4})\s*-\s*(\d{2}|\d{4})(?!\d)", t or "")
        if not m:
            continue
        a, b = int(m.group(1)), int(m.group(2))
        a = a + 2000 if a < 100 else a
        b = b + 2000 if b < 100 else b
        if b == a + 1 and 2015 <= a <= 2100:
            return a
    return None


def detect_program(*texts: str) -> str:
    for t in texts:
        k = _key(t)
        if "MASATEN" in k:
            return "MASA_TENISI"
        if "ALTYAPI" in k:
            return "ALTYAPI"
        if "SPOROKULU" in k:
            return "SPOR_OKULU"
    return "DIGER"


def detect_layout(values: list[list[object]], season_start: int, scan_rows: int = 12) -> SheetLayout | None:
    for r, row in enumerate(values[:scan_rows]):
        keys = [_key(c) for c in row]
        if "ADSOYAD" not in keys:
            continue
        cols: dict[str, int] = {}
        # Başlık önce ana satırda, bulunamazsa komşu alt/üst başlık satırında aranır
        # (Spor Okulu'nda tekstil "ÜCRET" bir alt satırda duruyor).
        neighbours = [keys] + [[_key(c) for c in values[j]] for j in (r + 1, r - 1) if 0 <= j < len(values)]
        for field_name, aliases in HEADER_ALIASES.items():
            for row_keys in neighbours:
                hit = next((i for i, k in enumerate(row_keys) if k in aliases), None)
                if hit is not None:
                    cols[field_name] = hit
                    break
        months: list[tuple[int, date]] = []
        year, prev = season_start, None
        for i, k in enumerate(keys):
            if i <= cols["name"]:
                continue
            m = _MONTH_INDEX.get(k)
            if m is None:
                continue
            if prev is not None and m <= prev:
                year += 1
            if not months and m < 7:  # sezon Temmuz'dan önce başlamaz
                year = season_start + 1
            months.append((i, date(year, m, 1)))
            prev = m
        if not months:
            return None
        if "note" not in cols:  # Altyapı'da açıklama sütununun başlığı yok: son aydan sonraki sütun
            cols["note"] = months[-1][0] + 1
        return SheetLayout(header_row=r, columns=cols, month_columns=months)
    return None


# ── Satır ayrıştırma ─────────────────────────────────────────────────────────


@dataclass
class Cell:
    month: date
    status: str
    amount: Decimal | None
    raw: str


@dataclass
class IncomeRow:
    row_number: int  # 1-tabanlı (Sheets'teki satır no)
    key: str
    name: str
    record_no: str | None
    team: str | None
    coach: str | None
    birth_year: int | None
    raw_payment_type: str
    payment_type: str
    textile_fee: Decimal | None
    note: str | None
    is_left: bool
    cells: list[Cell]

    @property
    def paid_total(self) -> Decimal:
        return sum((c.amount for c in self.cells if c.amount), Decimal("0"))

    @property
    def typical_fee(self) -> Decimal | None:
        """Aylık sporcunun olağan aidatı: ödenen tutarların medyanı (kısmi aylar sapmasın diye)."""
        amounts = [c.amount for c in self.cells if c.amount]
        return money(statistics.median(amounts)) if amounts else None


@dataclass
class ParseIssue:
    row_number: int | None
    name: str | None
    kind: str
    detail: str


@dataclass
class ParsedSheet:
    title: str
    program: str
    season_start: int
    months: list[date]
    rows: list[IncomeRow] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def season(self) -> str:
        return f"{self.season_start}-{str(self.season_start + 1)[2:]}"


def _cell(row: list[object], idx: int | None) -> object:
    return row[idx] if idx is not None and idx < len(row) else None


def _payment_type(raw: str, cells: list[Cell]) -> str:
    s = norm(raw)
    if "BURSLU" in s:
        return PARTIAL_SCHOLAR if "%" in s else FULL_SCHOLAR
    if s.startswith("SEZONLUK"):
        return SEASONAL
    if s.startswith("AYLIK"):
        return MONTHLY
    if any(m in s for m in PROSPECT_MARKERS):
        return PROSPECT
    # Tür yazılmamışsa hücrelerden çıkar
    statuses = Counter(c.status for c in cells)
    if statuses[SEASON] >= 3:
        return SEASONAL
    if statuses[SCHOLARSHIP] >= 3:
        return FULL_SCHOLAR
    if statuses[PLACEHOLDER] or statuses[PAID]:
        return MONTHLY
    return UNKNOWN


def parse_sheet(title: str, values: list[list[object]], *, default_season: int | None = None) -> ParsedSheet | None:
    """Bir sayfayı ayrıştırır. Ödeme tablosu değilse (ör. BİLANÇO) None döner."""
    head_text = " ".join(str(c) for row in values[:3] for c in row if c)
    season = detect_season(title) or detect_season(head_text) or default_season
    if season is None:
        return None
    layout = detect_layout(values, season)
    if layout is None:
        return None
    program = detect_program(title, head_text)
    sheet = ParsedSheet(title=title, program=program, season_start=season, months=[m for _, m in layout.month_columns])
    c = layout.columns
    seen: Counter[str] = Counter()

    for r in range(layout.header_row + 1, len(values)):
        row = values[r]
        name = re.sub(r"\s+", " ", str(_cell(row, c["name"]) or "")).strip()
        if not name or _key(name) == "ADSOYAD":
            continue
        cells: list[Cell] = []
        for col, month in layout.month_columns:
            raw = _cell(row, col)
            status, amount = classify_cell(raw)
            cells.append(Cell(month, status, amount, "" if raw is None else str(raw).strip()))
            if status == NOTE:
                sheet.issues.append(ParseIssue(r + 1, name, "unrecognized_cell", f"{month:%Y-%m}: '{raw}'"))
        raw_type = str(_cell(row, c.get("payment_type")) or "").strip()
        note = str(_cell(row, c.get("note")) or "").strip() or None
        ptype = _payment_type(raw_type, cells)
        flags = norm(f"{raw_type} {note or ''}")
        is_left = any(m in flags for m in LEFT_MARKERS)
        if ptype == UNKNOWN and not is_left:
            sheet.issues.append(
                ParseIssue(r + 1, name, "missing_payment_type", "Ödeme türü yok ve hücrelerden çıkarılamadı")
            )

        base = _key(name)
        seen[base] += 1
        key = base if seen[base] == 1 else f"{base}#{seen[base]}"
        if seen[base] == 2:
            sheet.issues.append(ParseIssue(r + 1, name, "duplicate_name", "Aynı isim sayfada birden fazla"))

        birth = str(_cell(row, c.get("birth_year")) or "").strip()
        sheet.rows.append(
            IncomeRow(
                row_number=r + 1,
                key=key,
                name=name,
                record_no=str(_cell(row, c.get("no")) or "").strip() or None,
                team=(str(_cell(row, c.get("team")) or "").strip() or None),
                coach=(str(_cell(row, c.get("coach")) or "").strip() or None),
                birth_year=int(float(birth)) if re.fullmatch(r"\d{4}(\.0)?", birth) else None,
                raw_payment_type=raw_type,
                payment_type=ptype,
                textile_fee=parse_amount(_cell(row, c.get("textile_fee"))),
                note=note,
                is_left=is_left,
                cells=cells,
            )
        )
    return sheet


# ── Beklenen ödeme ve gecikme ────────────────────────────────────────────────

DUE, PENDING_INSTALLMENT = "DUE", "PENDING_INSTALLMENT"


def expected_status(row: IncomeRow, month: date, today: date) -> str | None:
    """Bu ay için ödeme bekleniyor muydu ve yapılmadı mı?

    DUE                 → aylık sporcu, başlamış, ay geçmiş/içinde, hücre boş
    PENDING_INSTALLMENT → sezonluk sporcu, ay geçmiş/içinde, hücre boş (taksit)
    None                → beklenen bir şey yok ya da ödenmiş
    """
    if row.is_left or month > today.replace(day=1):
        return None
    cell = next((c for c in row.cells if c.month == month), None)
    if cell is None or cell.status != EMPTY:
        return None
    if row.payment_type == MONTHLY:
        # Başlangıç: baştaki "AYLIK" yer tutucularından sonraki ilk ay
        start = None
        for c in row.cells:
            if c.status == PLACEHOLDER:
                continue
            start = c.month
            break
        if start is None or month < start:
            return None
        # Son ödemeden sonra 2+ ay boşsa muhtemelen bırakmış; yine de listede kalsın ama işaretlensin
        return DUE
    if row.payment_type == SEASONAL:
        return PENDING_INSTALLMENT
    return None


@dataclass
class MonthTotals:
    month: date
    by_program: dict[str, Decimal]
    total: Decimal
    payers: int
    non_payers: int
    pending_installments: int


def monthly_totals(sheets: list[ParsedSheet], today: date) -> list[MonthTotals]:
    months = sorted({m for s in sheets for m in s.months})
    out: list[MonthTotals] = []
    for month in months:
        by_prog = {p: Decimal("0") for p in {s.program for s in sheets}}
        payers = non_payers = pending = 0
        for s in sheets:
            for row in s.rows:
                cell = next((c for c in row.cells if c.month == month), None)
                if cell and cell.amount:
                    by_prog[s.program] += cell.amount
                    payers += 1
                exp = expected_status(row, month, today)
                if exp == DUE:
                    non_payers += 1
                elif exp == PENDING_INSTALLMENT:
                    pending += 1
        out.append(
            MonthTotals(
                month=month,
                by_program=by_prog,
                total=sum(by_prog.values(), Decimal("0")),
                payers=payers,
                non_payers=non_payers,
                pending_installments=pending,
            )
        )
    return out


def head_counts(rows: list[IncomeRow]) -> dict[str, int]:
    active = [r for r in rows if not r.is_left and r.payment_type not in (PROSPECT, UNKNOWN)]
    c = Counter(r.payment_type for r in active)
    return {
        "active": len(active),
        "monthly": c[MONTHLY],
        "seasonal": c[SEASONAL],
        "scholarship": c[FULL_SCHOLAR],
        "partialScholarship": c[PARTIAL_SCHOLAR],
        "prospects": sum(1 for r in rows if r.payment_type == PROSPECT and not r.is_left),
        "left": sum(1 for r in rows if r.is_left),
    }
