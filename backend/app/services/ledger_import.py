"""Excel tahsilat defteri (ör. "2025-2026 TAHSİLATLAR.xlsx") içe aktarma.

Defter yapısı: her ay ayrı sayfa ("TEMMUZ 25", "AĞUSTOS 26" ...), sütunlar
TARİH · OYUNCU AD SOYAD · GRUP · DÖNEM · TUTAR · AİDAT · FORMA · AÇIKLAMA(ödeme kanalı).
Sayfalar arasında sütun kayması, metin olarak girilmiş tutar ("₺4.700,00"),
hatalı tarih ("01.08.205") ve serbest metin dönem etiketi var. Bu modül:

- her satırı sınıflandırır (aylık / kısmi / çok aylık / sezonluk peşin / taksit /
  tekstil / etkinlik / gecikmiş borç),
- etiketteki ayları takvim aylarına çevirir (yıl, sayfa ayına en yakın seçilir),
- düzelttiği her şeyi anomali olarak raporlar — veri sessizce "temizlenmez".

Saf fonksiyon: dosya okur, veritabanına dokunmaz (yazma: services/ledger_store.py).
"""
from __future__ import annotations

import io
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import BinaryIO

import openpyxl

MONTHS = ["OCAK", "SUBAT", "MART", "NISAN", "MAYIS", "HAZIRAN", "TEMMUZ", "AGUSTOS", "EYLUL", "EKIM", "KASIM", "ARALIK"]
_MONTH_RE = re.compile(r"(OCAK|SUBAT|MART|NISAN|MAYIS|HAZIRAN|TEMMUZ|AGUSTOS+|EYLUL|EKIM|KASIM|ARALIK)")
_TEXTILE = ("TEKSTIL", "TEKSITL", "FORMA", "TISORT", "CANTA", "CIFT TARAFLI")
_EVENT = ("ISTANBUL", "TRIBUN", "KAMP", "TURNUVA")


def fold(s: str) -> str:
    """Türkçe karakterleri ASCII'ye katlar, büyük harfe çevirir, boşlukları sadeleştirir.
    "Ağustos", "AĞUSTOS", "AGUSTOS" → "AGUSTOS"."""
    s = s.replace("i̇", "i").replace("ı", "I").replace("İ", "I")
    s = unicodedata.normalize("NFKD", s.upper())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s).strip()


def player_key(name: str) -> str:
    """Oyuncu eşleştirme anahtarı: yazım farklarına (boşluk, Türkçe karakter) dayanıklı."""
    return re.sub(r"[^A-Z ]", "", fold(name)).strip()


@dataclass
class LedgerRecord:
    sheet: str
    source_row: int  # Excel satır numarası (1 tabanlı) → kayda geri izlenebilirlik
    sheet_month: date
    paid_on: date
    paid_on_inferred: bool
    player_name: str
    player_key: str
    multi_player: bool
    group: str  # ALTYAPI | SPOR_OKULU | KIZ_TAKIMI | MASA_TENISI | KARMA | BILINMIYOR
    period_label: str
    kind: str  # MONTHLY | PARTIAL | MULTI_MONTH | SEASON_UPFRONT | SEASON_INSTALLMENT | TEXTILE | EVENT | ARREARS | OTHER
    covered_months: list[date]
    scholarship: bool
    amount: Decimal
    dues_amount: Decimal
    textile_amount: Decimal
    channel_raw: str
    channel: str  # POS | MAIL_ORDER | GARANTI | FINANSBANK | ISBANKASI | CASH | UNKNOWN
    method: str  # PaymentMethod enum değeri
    cancelled: bool
    note: str | None = None


@dataclass
class Anomaly:
    sheet: str
    source_row: int
    issue: str
    detail: str


@dataclass
class ParseResult:
    records: list[LedgerRecord] = field(default_factory=list)
    anomalies: list[Anomaly] = field(default_factory=list)
    sheets: list[str] = field(default_factory=list)


def parse_sheet_month(title: str) -> date | None:
    """'AĞUSTOS 25' → 2025-08-01."""
    m = re.match(r"^\s*([A-Z]+)\s+(\d{2,4})\s*$", fold(title))
    if not m:
        return None
    name = re.sub(r"S+$", "S", m.group(1))  # AGUSTOSS
    if name not in MONTHS:
        return None
    y = int(m.group(2))
    return date(2000 + y if y < 100 else y, MONTHS.index(name) + 1, 1)


def parse_money(v) -> Decimal | None:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return Decimal(str(round(v, 2)))
    s = str(v).strip().replace("₺", "").replace("TL", "").strip()
    if s in ("", "-"):
        return None
    if "," in s and "." in s:  # son ayraç ondalıktır: 4.700,00 (TR) / 5,200.00 (EN)
        dec = "," if s.rfind(",") > s.rfind(".") else "."
        s = s.replace("." if dec == "," else ",", "").replace(dec, ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def _months_between(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + a.month - b.month


def parse_date(v, sheet_month: date) -> tuple[date, bool, str | None]:
    """(tarih, çıkarım_mı, sorun). Sayfa ayından 2 aydan fazla sapan tarih hatalı sayılır
    ve sayfa ayının 1'ine düşülür (nakit hangi ayın defterinde ise o aya aittir)."""
    d: date | None = None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    elif v is not None:
        m = re.match(r"^\s*(\d{1,2})\s*[./\- ]\s*(\d{1,2})\s*[./\- ]\s*(\d{2,5})\s*$", str(v))
        if m:
            day, mon, yr = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if yr < 100:
                yr += 2000
            try:
                d = date(yr, mon, day) if yr < 10000 else None
            except ValueError:
                d = None
            if d is None or abs(_months_between(d, sheet_month)) > 2:
                # "01.08.205", "02.09.2010": gün/ay doğru, yıl bozuk → sayfanın yılıyla dene
                try:
                    fixed = date(sheet_month.year, mon, day)
                    if abs(_months_between(fixed, sheet_month)) <= 1:
                        return fixed, True, f"tarih düzeltildi: {v!r} → {fixed.isoformat()}"
                except ValueError:
                    pass
                d = None
    if d is None:
        return sheet_month, True, f"tarih okunamadı: {v!r}"
    if abs(_months_between(d, sheet_month)) > 2:
        return sheet_month, True, f"tarih sayfa ayıyla uyumsuz: {d.isoformat()}"
    return d, False, None


def normalize_group(raw) -> str:
    g = fold(str(raw or ""))
    has_school = "OKU" in g  # "SPOR OKUKU" yazım hatası dahil
    has_youth = bool(re.search(r"ALT\s*P?Y?A?P?I|ALTAPI|ALTPYAPI", g))
    if "KIZ" in g:
        return "KIZ_TAKIMI"
    if "MASA" in g and not has_school:
        return "MASA_TENISI"
    if has_school and (has_youth or "MASA" in g):
        return "KARMA"
    if has_school:
        return "SPOR_OKULU"
    if has_youth:
        return "ALTYAPI"
    return "BILINMIYOR"


def normalize_channel(raw) -> tuple[str, str]:
    """(kanal, PaymentMethod). Banka adı = o bankanın hesabına havale/EFT varsayımı."""
    c = fold(str(raw or ""))
    if "MAIL" in c:
        return "MAIL_ORDER", "CREDIT_CARD"
    if "POS" in c:
        return "POS", "CREDIT_CARD"
    if "GARA" in c:
        return "GARANTI", "BANK_TRANSFER"
    if "FINANS" in c:
        return "FINANSBANK", "BANK_TRANSFER"
    if "IS BANK" in c or "ISBANK" in c:
        return "ISBANKASI", "BANK_TRANSFER"
    if "NAKIT" in c:
        return "CASH", "CASH"
    return "UNKNOWN", "BANK_TRANSFER"


def resolve_month(name: str, sheet_month: date) -> date:
    """Etiketteki ay adını yıla oturtur: sayfa ayına en yakın takvim ayı (−9 … +3 ay penceresi).
    'AĞUSTOS 25' sayfasında 'TEMMUZ' → 2025-07; 'OCAK 26' sayfasında 'ARALIK' → 2025-12."""
    mi = MONTHS.index(re.sub(r"S+$", "S", name)) + 1
    best = None
    for y in (sheet_month.year - 1, sheet_month.year, sheet_month.year + 1):
        cand = date(y, mi, 1)
        diff = _months_between(cand, sheet_month)
        if -9 <= diff <= 3 and (best is None or abs(diff) < abs(_months_between(best, sheet_month))):
            best = cand
    return best or date(sheet_month.year, mi, 1)


def classify(label: str, sheet_month: date) -> tuple[str, list[date], bool, bool]:
    """(tür, kapsanan aylar, burslu_mu, iptal_mi)."""
    f = fold(label)
    cancelled = "IPTAL" in f
    scholarship = "BURS" in f
    months = []
    for m in _MONTH_RE.findall(f):
        d = resolve_month(m, sheet_month)
        if d not in months:
            months.append(d)
    months.sort()
    if "SEZON" in f or "PESIN" in f or "TAKSIT" in f or "YARISI" in f:
        installment = "TAKSIT" in f or "YARISI" in f or "KALAN" in f or "%50" in f
        return ("SEASON_INSTALLMENT" if installment else "SEASON_UPFRONT"), months, scholarship, cancelled
    if "BORC" in f or "GECIKMIS" in f:
        return "ARREARS", months, scholarship, cancelled
    if months:
        if any(k in f for k in ("YARIM", "EKSIK", "KALAN", "EK ODEME", "GERI KALAN", "250 TL")):
            return "PARTIAL", months, scholarship, cancelled
        return ("MULTI_MONTH" if len(months) > 1 else "MONTHLY"), months, scholarship, cancelled
    if any(k in f for k in _EVENT):
        return "EVENT", months, scholarship, cancelled
    if any(k in f for k in _TEXTILE):
        return "TEXTILE", months, scholarship, cancelled
    return "OTHER", months, scholarship, cancelled


def _header(rows: list[tuple]) -> tuple[int, int] | None:
    """('OYUNCU AD SOYAD' satırı, sütunu). Bazı sayfalar A, bazıları B sütunundan başlıyor."""
    for i, r in enumerate(rows[:10]):
        for j, c in enumerate(r or ()):
            if c is not None and fold(str(c)) == "OYUNCU AD SOYAD":
                return i, j
    return None


def parse_workbook(source: str | bytes | BinaryIO) -> ParseResult:
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    wb = openpyxl.load_workbook(source, data_only=True, read_only=True)
    out = ParseResult()
    for ws in wb.worksheets:
        sheet_month = parse_sheet_month(ws.title)
        if sheet_month is None:
            out.anomalies.append(Anomaly(ws.title, 0, "sayfa_atlandi", "Sayfa adı 'AY YY' biçiminde değil"))
            continue
        rows = list(ws.iter_rows(values_only=True))
        hdr = _header(rows)
        if hdr is None:
            out.anomalies.append(Anomaly(ws.title, 0, "sayfa_atlandi", "Başlık satırı bulunamadı"))
            continue
        out.sheets.append(ws.title)
        hi, ni = hdr
        for idx in range(hi + 1, len(rows)):
            r = tuple(rows[idx] or ())
            cells = (list(r[ni - 1: ni + 7]) + [None] * 8)[:8] if ni >= 1 else [None, *(list(r[ni: ni + 7]) + [None] * 7)[:7]]
            raw_date, raw_name, raw_group, raw_label, raw_amount, raw_dues, raw_textile, raw_channel = cells
            if raw_name is None or not str(raw_name).strip():
                continue
            row_no = idx + 1
            name = re.sub(r"\s+", " ", str(raw_name)).strip().upper()
            label = re.sub(r"\s+", " ", str(raw_label or "")).strip()

            def warn(issue: str, detail: str, _sheet=ws.title, _row=row_no):
                out.anomalies.append(Anomaly(_sheet, _row, issue, detail))

            paid_on, inferred, date_issue = parse_date(raw_date, sheet_month)
            if date_issue:
                warn("tarih", date_issue)
            kind, covered, scholarship, cancelled = classify(label, sheet_month)
            amount, dues, textile = parse_money(raw_amount), parse_money(raw_dues), parse_money(raw_textile)
            if amount is None:
                if dues is None and textile is None:
                    warn("tutar_yok", f"TUTAR={raw_amount!r}, satır atlandı")
                    continue
                amount = (dues or Decimal(0)) + (textile or Decimal(0))
                warn("tutar", f"TUTAR={raw_amount!r} okunamadı; AİDAT+FORMA={amount} kullanıldı")
            if dues is None and textile is None:
                if kind == "TEXTILE":
                    dues, textile = Decimal(0), amount
                else:
                    dues, textile = amount, Decimal(0)
            else:
                dues, textile = dues or Decimal(0), textile or Decimal(0)
                if dues + textile != amount:
                    if textile > 0 or any(k in fold(label) for k in _TEXTILE):
                        # Tekstil içeren satır: aidat sütunu güvenilir, fark tekstildir.
                        warn("tutar_uyumsuz", f"TUTAR {amount} ≠ AİDAT {dues} + FORMA {textile}; FORMA=TUTAR−AİDAT alındı")
                        textile = max(Decimal(0), amount - dues)
                        dues = amount - textile
                    else:
                        # Tekstilsiz satırda iki sütundan biri yazım hatası (6520↔6250, 170000↔72000).
                        # Geliri şişirmemek için küçük olan alınır; satır manuel kontrole düşer.
                        kept = min(amount, dues + textile)
                        warn("tutar_uyumsuz", f"TUTAR {amount} ≠ AİDAT {dues}; küçük olan {kept} alındı — kontrol edin")
                        amount, dues, textile = kept, kept, Decimal(0)
            if amount <= 0:
                warn("tutar_sifir", f"tutar {amount}, satır atlandı")
                continue
            channel, method = normalize_channel(raw_channel)
            if channel == "UNKNOWN":
                warn("kanal", f"ödeme kanalı tanınmadı: {raw_channel!r}")
            group = normalize_group(raw_group)
            if group == "BILINMIYOR":
                warn("grup", f"grup tanınmadı: {raw_group!r}")
            if cancelled:
                warn("iptal", f"'{label}' — toplamlara dahil edilmedi")
            if kind == "OTHER" and not cancelled:
                warn("donem_etiketi", f"sınıflandırılamadı: '{label}'")
            note = " ".join(str(c).strip() for c in r[ni + 7:] if c not in (None, "") and str(c).strip()) or None
            out.records.append(LedgerRecord(
                sheet=ws.title, source_row=row_no, sheet_month=sheet_month, paid_on=paid_on,
                paid_on_inferred=inferred, player_name=name, player_key=player_key(name),
                multi_player=bool(re.search(r"\s[-+]\s?|\s-|\bVE\b", name)), group=group, period_label=label,
                kind=kind, covered_months=covered, scholarship=scholarship, amount=amount, dues_amount=dues,
                textile_amount=textile, channel_raw=str(raw_channel or "").strip(), channel=channel,
                method=method, cancelled=cancelled, note=note))
    return out
