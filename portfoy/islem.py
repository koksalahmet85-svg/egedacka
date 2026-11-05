"""Gerçekleşen işlemi kaydeder.
Kullanım: python3 islem.py AL SPY 0.512 585.20 [--dengeleme]
          python3 islem.py YATIR 1000 <katkıdan önceki portföy değeri $>
--dengeleme: bu işlem aylık/başlangıç dengelemesinin parçasıysa (son_dengeleme tarihini günceller)
"""
import json, sys, csv, datetime as dt
from strateji import KOK

d = json.loads((KOK / "portfoy.json").read_text())
if sys.argv[1].upper() == "YATIR":
    # python3 islem.py YATIR 1000 <mevcut_portfoy_degeri>  -> birim fiyattan yeni pay
    tutar, deger = float(sys.argv[2]), float(sys.argv[3])
    yeni = tutar / (deger / d["birim"])
    d["birim"] += yeni; d["nakit"] += tutar; d["yatirilan"] += tutar
    (KOK / "portfoy.json").write_text(json.dumps(d, indent=2, ensure_ascii=False))
    with open(KOK / "islemler.csv", "a", newline="") as f:
        csv.writer(f).writerow([dt.date.today(), "YATIR", "NAKIT", "", "", tutar, f"birim {yeni:.4f}"])
    sys.exit(f"Katkı kaydedildi: {tutar} $ | toplam yatırılan {d['yatirilan']} $")
islem, s, adet, fiyat = sys.argv[1].upper(), sys.argv[2].upper(), float(sys.argv[3]), float(sys.argv[4])
tutar = adet * fiyat
if islem == "AL":
    if tutar > d["nakit"] + 1:
        sys.exit(f"Yetersiz nakit: {d['nakit']:.2f} < {tutar:.2f}")
    d["nakit"] -= tutar
    d["pozisyonlar"][s] = d["pozisyonlar"].get(s, 0) + adet
elif islem == "SAT":
    if adet > d["pozisyonlar"].get(s, 0) + 1e-6:
        sys.exit(f"Elde {d['pozisyonlar'].get(s,0)} {s} var, {adet} satılamaz")
    d["nakit"] += tutar
    d["pozisyonlar"][s] -= adet
    if d["pozisyonlar"][s] < 1e-6:
        d["pozisyonlar"].pop(s); d["alt_sayac"].pop(s, None)
else:
    sys.exit("İşlem AL veya SAT olmalı")
if "--dengeleme" in sys.argv:
    d["son_dengeleme"] = str(dt.date.today())
(KOK / "portfoy.json").write_text(json.dumps(d, indent=2, ensure_ascii=False))
with open(KOK / "islemler.csv", "a", newline="") as f:
    csv.writer(f).writerow([dt.date.today(), islem, s, adet, fiyat, round(tutar, 2), ""])
print(f"Kaydedildi: {islem} {adet} {s} @ {fiyat} = {tutar:.2f} $ | Nakit: {d['nakit']:.2f} $")
