"""Gerçek "GENEL ÖDEME TABLOSU" düzenini taklit eden sentetik veri (isimler uydurmadır)."""

E = ""

SPOR_OKULU_TITLE = "26-27 Spor Okulu"
SPOR_OKULU = [
    ["SPOR OKULU GENEL ÖDEME LİSTESİ 2026-2027"],
    [
        "TEKSTİL PAKETİ",
        E,
        E,
        E,
        E,
        "GRUP ",
        "DOĞUM YILI",
        "ÖDEME TÜRÜ",
        "NO",
        "AD SOYAD",
        "TEMMUZ",
        "AĞUSTOS",
        "EYLÜL",
        "EKİM",
        "KASIM",
        "ARALIK",
        "OCAK",
        "ŞUBAT",
        "MART",
        "NİSAN",
        "MAYIS",
        "HAZİRAN",
        "TEMMUZ ",
        "AĞUSTOS",
        "AÇIKLAMA",
    ],
    ["TİŞÖRT", "ÇİFT TARAFLI", "HOODİE", "ÇANTA", "ÜCRET"],
    # 1) sezonluk, Temmuz'da tek ödeme
    [E, E, E, E, "-", "SPOR OKULU", "2016", "SEZONLUK", "1", "ALİ DEMO", "90.000,00 TRY"] + ["SEZONLUK"] * 13,
    # 2) sezonluk 2 taksit, Ekim taksiti henüz yok
    [
        E,
        E,
        E,
        E,
        "-",
        "SPOR OKULU",
        "2017",
        "SEZONLUK",
        "2",
        "VELİ ÖRNEK",
        "45.000,00 TRY",
        "SEZONLUK",
        "45.000,00 TRY",
        E,
        "SEZONLUK",
    ],
    # 3) aylık, Eylül'de başladı, ödüyor
    [
        E,
        E,
        E,
        E,
        "6.000,00 TRY",
        "SPOR OKULU",
        "2016",
        "AYLIK",
        "3",
        "CAN TEST",
        "AYLIK",
        "AYLIK",
        "8.100,00 TRY",
        "8.100,00 TRY",
    ],
    # 4) aylık, Eylül ödedi, Ekim boş → bu ay bekleniyor
    [E, E, E, E, "6.000,00 TRY", "SPOR OKULU", "2018", "AYLIK", "4", "DENİZ BOŞ", "AYLIK", "AYLIK", "9.000,00 TRY", E],
    # 5) aylık, hiç ödememiş (Eylül + Ekim borçlu)
    [E, E, E, E, "6.000,00 TRY", "SPOR OKULU", "2018", "AYLIK", "5", "EGE BORÇLU", "AYLIK", "AYLIK"],
    # 6) aylık, Ekim'de başlıyor (daha başlamadı)
    [
        E,
        E,
        E,
        E,
        "6.000,00 TRY",
        "SPOR OKULU",
        "2017",
        "AYLIK",
        "6",
        "MERT YENİ",
        "AYLIK",
        "AYLIK",
        "AYLIK",
        "4.050,00 TRY",
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        "DAHA BAŞLAMADI",
    ],
    # 7) bıraktı → borçlu sayılmaz
    [
        E,
        E,
        E,
        E,
        "6.000,00 TRY",
        "SPOR OKULU",
        "2017",
        "AYLIK",
        "7",
        "ARDA GİTTİ",
        "AYLIK",
        "AYLIK",
        "8.100,00 TRY",
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        "BIRAKTI",
    ],
    # 8) aynı isim ikinci kez
    [E, E, E, E, "6.000,00 TRY", "SPOR OKULU", "2016", "AYLIK", "8", "CAN TEST", "AYLIK", "AYLIK", "₺8.100", "8.100"],
]

ALTYAPI_TITLE = "2026-2027 Altyapı"
_MONTHS = [
    "TEMMUZ",
    "AĞUSTOS",
    "EYLÜL",
    "EKİM",
    "KASIM",
    "ARALIK",
    "OCAK",
    "ŞUBAT",
    "MART",
    "NİSAN",
    "MAYIS",
    "HAZİRAN",
    "TEMMUZ ",
    "AĞUSTOS",
]
ALTYAPI = [
    ["ALTYAPI GENEL ÖDEME LİSTESİ 2026-2027"],
    ["TEKSTİL PAKETİ"],
    [
        "TİŞÖRT",
        "ÇİFT TARAFLI",
        "HOODİE",
        "MAÇ FORMASI",
        "WARM UP",
        "ÇANTA",
        "ÜCRET",
        "TAKIM İSMİ",
        "KOÇ",
        "DOĞUM YILI",
        "ÖDEME TÜRÜ",
        "NO",
        "AD SOYAD",
        *_MONTHS,
    ],
    [E] * 6
    + ["-", "EGE ALFA U-10 A ", "KOÇ A", "2017", "SEZONLUK", "1", "ATLAS SEZON", "119.000,00 TRY"]
    + ["SEZONLUK"] * 13,
    [E] * 6
    + [E, "EGE ALFA U-10 A ", "KOÇ A", "2017", "BURSLU", "2", "KEMAL BURS"]
    + ["BURSLU"] * 14
    + ["BURSLU ALPER KOÇ BİLGİSİNDE"],
    [E] * 6
    + [
        "10.000,00 TRY",
        "EGE ALFA U-10 A ",
        "KOÇ A",
        "2017",
        "AYLIK",
        "3",
        "UZAY AY",
        "AYLIK",
        "AYLIK",
        "9.900,00 TRY",
        "9.900,00 TRY",
    ],
    [E] * 6
    + ["-", "EGE ÜNİ. U-14 B", "KOÇ B", "2014", "%50 BURSLU", "4", "METE YARIM", "%50 BURSLU", "53.500,00 TRY"]
    + ["%50 BURSLU"] * 12,
    [E] * 6
    + [
        E,
        "EGE ÜNİ. U-14 B",
        "KOÇ B",
        "2014",
        "AYLIK",
        "5",
        "ÇAĞAN GEÇ",
        "AYLIK",
        "AYLIK",
        E,
        "19.800,00 TRY",
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        E,
        "EYLÜL+EKİM BİRLİKTE",
    ],
    # Ödeme türü boş, hücre yok → sorun listesine
    [E] * 6 + [E, "EGE ALFA U-14 A", "KOÇ C", "2014", E, E, "NAZIM EKSİK"],
    [E] * 6 + [E, "EGE ALFA U-14 A", "KOÇ C", "2014", "AYLIK", "6", "ARAS GELMEDİ", "AYLIK", "AYLIK", "GELMEDİ"],
]

MASA_TITLE = "MASA TENİSİ"
MASA = [
    ["SPOR OKULU GENEL ÖDEME LİSTESİ 2026-2027"],  # kopyalanmış başlık: program sayfa adından gelir
    ["TEKSTİL PAKETİ", E, E, E, E, "GRUP ", "DOĞUM YILI", "ÖDEME TÜRÜ", "NO", "AD SOYAD", *_MONTHS, "AÇIKLAMA"],
    ["TİŞÖRT", "ÇİFT TARAFLI", "HOODİE", "ÇANTA", "ÜCRET"],
    [
        E,
        E,
        E,
        "*",
        "6.000,00 TRY",
        "MASA TENİSİ",
        "2017",
        E,
        "1",
        "UMUT RAKET",
        "AYLIK",
        "AYLIK",
        "₺13.000,00",
        E,
        "₺13.000,00",
    ],
    [E, E, E, E, E, "MASA TENİSİ", E, "ARANACAK", "2", "BORA ADAY", "AYLIK", "AYLIK", "₺9.000,00"],
]

BILANCO_TITLE = "BİLANÇO 26-27"
BILANCO = [
    [E, "26-27 GENEL GELİR TABLOSU"],
    [],
    [E, "AYLAR", "SPOR OKULU", "ALT YAPI", "TEKSTİL", "TEKSTİL ALT YAPI", "ÖDEYEN KİŞİSAYISI", "ÖDEMEYEN KİŞİ SAYISI"],
    [E, "Temmuz"],
]

OLD_TITLE = "spor okulu"  # sezon bilgisi yok → atlanır
OLD = [
    [E, "SPOR OKULU GENEL ÖDEME LİSTESİ"],
    ["ÖDEME TERCİH", "NO", "AD - SOYAD", "TEMMUZ ", "AĞUSTOS"],
    ["S", "4", "ESKİ KAYIT", "₺20.000,00"],
]

SPREADSHEET = {
    SPOR_OKULU_TITLE: SPOR_OKULU,
    ALTYAPI_TITLE: ALTYAPI,
    MASA_TITLE: MASA,
    BILANCO_TITLE: BILANCO,
    OLD_TITLE: OLD,
}
