"""Her sabah çalışır: dünkü kapanışlarla portföyü değerler, kural tetiklenirse emir listesi üretir.
Kullanım: python3 gunluk.py      -> raporu yazdırır ve raporlar/YYYY-MM-DD.md'ye kaydeder
"""
import json, datetime as dt
from pathlib import Path
from strateji import veri, hedef_agirlik, RISKLI, ESIK, KOK

DURUM = KOK / "portfoy.json"


def main():
    d = json.loads(DURUM.read_text())
    adj, cls = veri("2y")
    son = adj.index[-1]
    fiyat = cls.iloc[-1]
    sma200 = adj.iloc[-200:].mean()

    poz = d["pozisyonlar"]
    deger = d["nakit"] + sum(a * fiyat[s] for s, a in poz.items())
    # birim (fon payı) muhasebesi: aylık katkılar getiriyi şişirmesin
    birim_deger = deger / d["birim"]
    d["zirve_birim"] = max(d.get("zirve_birim", 1.0), birim_deger)
    dd = birim_deger / d["zirve_birim"] - 1
    kz = birim_deger - 1
    mevcut_w = {s: a * fiyat[s] / deger for s, a in poz.items()}
    if d["nakit"] > 0.5:
        mevcut_w["NAKİT"] = d["nakit"] / deger

    # 3 kapanış kuralı sayaçları (her kapanış günü bir kez sayılır)
    if d.get("son_sayac_gunu") != str(son.date()):
        for s in [s for s in poz if s in RISKLI]:
            alt = adj[s].iloc[-1] < sma200[s]
            d["alt_sayac"][s] = d["alt_sayac"].get(s, 0) + 1 if alt else 0
        d["son_sayac_gunu"] = str(son.date())

    hedef, tablo, _ = hedef_agirlik(adj)
    sebep = None
    if not poz:
        sebep = "BAŞLANGIÇ — portföy ilk kez kuruluyor"
    elif d["son_dengeleme"] is None or d["son_dengeleme"][:7] != str(son.date())[:7]:
        sebep = "AYLIK YENİDEN DENGELEME"
    else:
        cik = [s for s in poz if s in RISKLI and d["alt_sayac"].get(s, 0) >= 3]
        if cik:
            sebep = f"TREND ÇIKIŞI — {', '.join(cik)} 3 kapanıştır 200 günlük ortalamanın altında"
            hedef = {s: w for s, w in mevcut_w.items() if s not in cik and s != "NAKİT"}
            hedef["BIL"] = hedef.get("BIL", 0) + sum(mevcut_w.get(s, 0) for s in cik) + mevcut_w.get("NAKİT", 0)
        elif d["nakit"] / deger > ESIK:
            sebep = "KATKI — yeni para hedef ağırlıklara göre yerleştiriliyor (satış yok)"

    emirler = []
    if sebep and sebep.startswith("KATKI"):
        acik = {s: max(0.0, w * deger - poz.get(s, 0) * fiyat[s]) for s, w in hedef.items()}
        top = sum(acik.values()) or 1
        for s, a in acik.items():
            tutar = a / top * d["nakit"]
            if tutar >= 10:
                emirler.append(("AL", s, tutar / fiyat[s], fiyat[s], tutar))
    elif sebep:
        semb = (set(hedef) | set(poz))
        fark = max(abs(hedef.get(s, 0) - mevcut_w.get(s, 0)) for s in semb)
        if sebep.startswith("AYLIK") and fark < ESIK and set(hedef) == set(poz):
            sebep += " — fark < %5, işlem gerekmiyor"
        else:
            for s in sorted(semb, key=lambda s: hedef.get(s, 0) - mevcut_w.get(s, 0)):  # önce satışlar
                hedef_adet = hedef.get(s, 0) * deger / fiyat[s]
                delta = hedef_adet - poz.get(s, 0)
                if abs(delta * fiyat[s]) < 10:
                    continue
                emirler.append((("SAT" if delta < 0 else "AL"), s, abs(delta), fiyat[s], abs(delta) * fiyat[s]))

    L = [f"# Cloue Portföy — {dt.date.today()} (son kapanış: {son.date()})", "",
         f"**Değer:** {deger:,.2f} $ | **Yatırılan:** {d['yatirilan']:,.0f} $ | **Getiri (birim bazlı):** {kz:+.2%} | **Zirveden düşüş:** {dd:.2%}", ""]
    if emirler:
        L += [f"## ⚠️ İŞLEM GÜNÜ: {sebep}", "",
              "Emirler (önce satışları gir; ABD açılışı 17:30 TSİ'den ~15 dk sonra, limit emir: alışta son fiyat +%0,2, satışta −%0,2):", "",
              "| İşlem | Sembol | Adet | Ref. fiyat | Tutar |", "|---|---|---|---|---|"]
        L += [f"| {i} | {s} | {a:.3f} | {p:.2f} | {t:,.2f} $ |" for i, s, a, p, t in emirler]
        if any(s.endswith("-USD") for _, s, *_ in emirler):
            L += ["", "Kripto satırları (BTC-USD, ETH-USD) **Midas Kripto** hesabında, dolar tutarının TL karşılığıyla girilir; 7/24 açık. ETF'ler Midas Yatırım'da (ABD seansı)."]
        L += ["", "İşlemleri yapınca gerçekleşen **adet ve fiyatları** bana yaz, kaydı ben güncelleyeceğim."]
    else:
        L += ["## ✅ Bugün işlem yok", "", f"Durum: {sebep or 'kurallar tetiklenmedi'}. Ekrana bakma, panik satışı yapma."]
    L += ["", "### Pozisyonlar", "| Sembol | Adet | Fiyat | Değer | Ağırlık | 200g ort. üstü? |", "|---|---|---|---|---|---|"]
    for s, a in poz.items():
        L.append(f"| {s} | {a:.3f} | {fiyat[s]:.2f} | {a*fiyat[s]:,.2f} | {a*fiyat[s]/deger:.1%} | {'evet' if adj[s].iloc[-1] > sma200[s] else 'HAYIR (' + str(d['alt_sayac'].get(s,0)) + '/3)'} |")
    L.append(f"| Nakit | | | {d['nakit']:,.2f} | {d['nakit']/deger:.1%} | |")
    L += ["", "### Sinyal tablosu (momentum skoru = 1/3/6/12 ay ort.)", "| Sembol | Skor | Trend | Vol (60g) | Hedef ağırlık |", "|---|---|---|---|---|"]
    for s in tablo.sort_values("skor", ascending=False).index:
        r = tablo.loc[s]
        L.append(f"| {s} | {r['skor']:+.1%} | {'↑' if r['fiyat>SMA200'] else '↓'} | {r['vol60']:.1%} | {hedef.get(s,0):.1%} |")
    rapor = "\n".join(L)
    (KOK / "raporlar" / f"{dt.date.today()}.md").write_text(rapor)
    DURUM.write_text(json.dumps(d, indent=2, ensure_ascii=False))
    print(rapor)


if __name__ == "__main__":
    main()
