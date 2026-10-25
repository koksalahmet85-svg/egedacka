from datetime import date
from decimal import Decimal

import pytest

from app.domain.drive_income import (
    DUE,
    EMPTY,
    NOTE,
    PAID,
    PENDING_INSTALLMENT,
    PLACEHOLDER,
    SCHOLARSHIP,
    SEASON,
    classify_cell,
    detect_program,
    detect_season,
    expected_status,
    head_counts,
    monthly_totals,
    parse_amount,
    parse_sheet,
)

from . import drive_fixtures as fx

TODAY = date(2026, 10, 25)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("45.000,00 TRY", "45000.00"),
        ("₺13.000,00", "13000.00"),
        ("₺19.800", "19800.00"),
        ("2.600", "2600.00"),
        ("650,00 TRY", "650.00"),
        ("8100", "8100.00"),
        (8100.0, "8100.00"),
        (119000, "119000.00"),
        ("  4.050,00 TRY ", "4050.00"),
        ("₺39,000.00", "39000.00"),  # kamp tablolarındaki İngilizce biçim
        ("£1,100.00", "1100.00"),
        ("362.6", "362.60"),  # bireysel ders "EK ÖDEMELER"
        ("102,65", "102.65"),
        ("1.234.567,89", "1234567.89"),
    ],
)
def test_parse_amount_formats(raw, expected):
    assert parse_amount(raw) == Decimal(expected)


@pytest.mark.parametrize("raw", ["SEZONLUK", "AYLIK", "", None, "-", ".", "%50 BURSLU", "GELMEDİ", 0, "₺0"])
def test_parse_amount_rejects_non_amounts(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize(
    "raw,status",
    [
        ("SEZONLUK", SEASON),
        ("sezonluk", SEASON),
        ("BURSLU", SCHOLARSHIP),
        ("%50 BURSLU", SCHOLARSHIP),
        ("AYLIK", PLACEHOLDER),
        ("", EMPTY),
        (".", EMPTY),
        ("₺0", EMPTY),
        ("GELMEDİ", NOTE),
        ("9.900,00 TRY", PAID),
    ],
)
def test_classify_cell(raw, status):
    assert classify_cell(raw)[0] == status


def test_season_and_program_detection():
    assert detect_season("26-27 Spor Okulu") == 2026
    assert detect_season("2026-2027 Altyapı") == 2026
    assert detect_season("SPOR OKULU GENEL ÖDEME LİSTESİ 2025- 2026") == 2025
    assert detect_season("BİLANÇO") is None
    assert detect_season("U14-2014") is None
    assert detect_program("26-27 Spor Okulu") == "SPOR_OKULU"
    assert detect_program("2026-2027 Altyapı") == "ALTYAPI"
    assert detect_program("Alt yapı") == "ALTYAPI"
    assert detect_program("MASA TENİSİ", "SPOR OKULU GENEL ÖDEME LİSTESİ") == "MASA_TENISI"


def _sheets():
    return {t: parse_sheet(t, v) for t, v in fx.SPREADSHEET.items()}


def test_non_payment_sheets_are_skipped():
    s = _sheets()
    assert s[fx.BILANCO_TITLE] is None
    assert s[fx.OLD_TITLE] is None  # sezon bilinmiyor
    assert parse_sheet(fx.OLD_TITLE, fx.OLD, default_season=2024) is not None


def test_spor_okulu_layout_and_months():
    sheet = _sheets()[fx.SPOR_OKULU_TITLE]
    assert sheet.program == "SPOR_OKULU" and sheet.season == "2026-27"
    assert sheet.months[0] == date(2026, 7, 1)
    assert sheet.months[5] == date(2026, 12, 1)
    assert sheet.months[6] == date(2027, 1, 1)
    assert sheet.months[-1] == date(2027, 8, 1) and len(sheet.months) == 14
    rows = {r.key: r for r in sheet.rows}
    ali = rows["ALİDEMO"]
    assert ali.payment_type == "SEZONLUK" and ali.paid_total == Decimal("90000.00")
    can = rows["CANTEST"]
    assert can.textile_fee == Decimal("6000.00")  # alt başlık satırındaki ÜCRET bulundu
    assert can.typical_fee == Decimal("8100.00")
    assert "CANTEST#2" in rows  # tekrar eden isim ayrı anahtar alır
    assert rows["ARDAGİTTİ"].is_left


def test_altyapi_layout_unheaded_note_and_team():
    sheet = _sheets()[fx.ALTYAPI_TITLE]
    assert sheet.program == "ALTYAPI"
    rows = {r.key: r for r in sheet.rows}
    assert rows["ATLASSEZON"].team == "EGE ALFA U-10 A" and rows["ATLASSEZON"].coach == "KOÇ A"
    assert rows["KEMALBURS"].payment_type == "BURSLU"
    assert rows["KEMALBURS"].note == "BURSLU ALPER KOÇ BİLGİSİNDE"  # başlıksız açıklama sütunu
    assert rows["METEYARIM"].payment_type == "KISMI_BURSLU"
    assert rows["METEYARIM"].paid_total == Decimal("53500.00")
    kinds = {(i.name, i.kind) for i in sheet.issues}
    assert ("NAZIM EKSİK", "missing_payment_type") in kinds
    assert ("ARAS GELMEDİ", "unrecognized_cell") in kinds


def test_masa_tenisi_program_from_sheet_title_and_prospect():
    sheet = _sheets()[fx.MASA_TITLE]
    assert sheet.program == "MASA_TENISI" and sheet.season_start == 2026
    rows = {r.key: r for r in sheet.rows}
    assert rows["UMUTRAKET"].payment_type == "AYLIK"  # tür boş → hücrelerden çıkarıldı
    assert rows["UMUTRAKET"].paid_total == Decimal("26000.00")
    assert rows["BORAADAY"].payment_type == "ADAY"


def test_expected_status_rules():
    rows = {r.key: r for r in _sheets()[fx.SPOR_OKULU_TITLE].rows}
    sep, oct_, nov = date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1)
    assert expected_status(rows["CANTEST"], oct_, TODAY) is None  # ödemiş
    assert expected_status(rows["DENİZBOŞ"], oct_, TODAY) == DUE
    assert expected_status(rows["EGEBORÇLU"], sep, TODAY) == DUE
    assert expected_status(rows["EGEBORÇLU"], oct_, TODAY) == DUE
    assert expected_status(rows["EGEBORÇLU"], nov, TODAY) is None  # gelecek ay
    assert expected_status(rows["MERTYENİ"], sep, TODAY) is None  # henüz başlamamıştı
    assert expected_status(rows["ARDAGİTTİ"], oct_, TODAY) is None  # bıraktı
    assert expected_status(rows["VELİÖRNEK"], oct_, TODAY) == PENDING_INSTALLMENT


def test_monthly_totals_match_bilanco_columns():
    sheets = [s for s in _sheets().values() if s]
    totals = {t.month: t for t in monthly_totals(sheets, TODAY)}
    jul, sep, oct_ = totals[date(2026, 7, 1)], totals[date(2026, 9, 1)], totals[date(2026, 10, 1)]
    assert jul.by_program["SPOR_OKULU"] == Decimal("135000.00")  # 90k + 45k
    assert jul.by_program["ALTYAPI"] == Decimal("119000.00")
    # Eylül: spor okulu 45.000 + 8.100 + 9.000 + 8.100 + 8.100 = 78.300
    assert sep.by_program["SPOR_OKULU"] == Decimal("78300.00")
    assert sep.by_program["MASA_TENISI"] == Decimal("22000.00")
    assert sep.total == sep.by_program["SPOR_OKULU"] + sep.by_program["ALTYAPI"] + sep.by_program["MASA_TENISI"]
    # Ekim ödemeyenler: DENİZ BOŞ, EGE BORÇLU, UMUT RAKET, ARAS GELMEDİ (Eylül'de "GELMEDİ", Ekim boş)
    # Bırakanlar ve adaylar sayılmaz.
    assert oct_.non_payers == 4
    assert oct_.pending_installments == 1  # VELİ ÖRNEK taksit
    assert totals[date(2026, 11, 1)].non_payers == 0  # gelecek


def test_head_counts():
    rows = [r for s in _sheets().values() if s for r in s.rows]
    c = head_counts(rows)
    assert c["left"] == 1 and c["scholarship"] == 1 and c["partialScholarship"] == 1
    assert c["prospects"] == 1
    assert c["seasonal"] == 3
