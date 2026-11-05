"""
Cloue Portföy Sistemi — kural tabanlı, kanıta dayalı ETF rotasyonu.

Kurallar (değiştirmeden önce backtest et):
  1. Evren: SPY, QQQ, VEA, VWO, GLD, BTC, ETH (riskli)  |  IEF, BIL (savunma)
     Kripto toplamı en fazla %20 (BTC/ETH maks. düşüşleri −%83/−%94).
     Kripto zaman serisi momentumu: Liu & Tsyvinski 2021, RFS.
  2. Momentum skoru = 1, 3, 6, 12 aylık getirilerin ortalaması
     (Jegadeesh & Titman 1993; Moskowitz, Ooi & Pedersen 2012)
  3. Trend filtresi: fiyat > 200 günlük ortalama VE skor > 0
     (Faber 2007, "A Quantitative Approach to Tactical Asset Allocation")
  4. Uygun olanlardan en iyi 3'ü, ters-volatiliteyle ağırlıklandırılır.
     Dolmayan slotlar -> IEF (trendi pozitifse) yoksa BIL (nakit).
  5. (Volatilite hedefi kodda var ama KAPALI: VOL_HEDEF=9. Backtest'te fayda göstermedi.)
  6. Yeniden dengeleme: ayın ilk işlem günü. Ağırlık farkı < %5 ise işlem yok.
  7. Ara kontrol (günlük): elde tutulan riskli varlık 3 kapanış üst üste
     200 günlük ortalamanın altında kapanırsa -> sat, BIL'e geç.
"""
import json, math, sys, datetime as dt
from pathlib import Path
import urllib.request
import numpy as np
import pandas as pd

import os
KRIPTO = ["BTC-USD", "ETH-USD"] if os.environ.get("KRIPTO", "1") == "1" else []
KRIPTO_MAX = 0.20   # kripto toplamı portföyün en fazla %20'si
RISKLI = ["SPY", "QQQ", "VEA", "VWO", "GLD"] + KRIPTO
SAVUNMA = ["IEF", "BIL"]
EVREN = RISKLI + SAVUNMA
import os
TOP_N, VOL_HEDEF, ESIK = 3, float(os.environ.get("VOL_HEDEF", 9)), 0.05
GUNLUK_KURAL = os.environ.get("GUNLUK_KURAL", "1") == "1"
KOK = Path(__file__).parent


def fiyat_cek(sembol, aralik="2y"):
    if aralik == "max":
        q = f"period1=1167609600&period2={int(dt.datetime.now().timestamp())}"
    else:
        q = f"range={aralik}"
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}"
           f"?{q}&interval=1d&events=div%2Csplit")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)["chart"]["result"][0]
    ts = pd.to_datetime(j["timestamp"], unit="s").normalize()
    adj = j["indicators"]["adjclose"][0]["adjclose"]
    cls = j["indicators"]["quote"][0]["close"]
    df = pd.DataFrame({"adj": adj, "close": cls}, index=ts).dropna()
    return df[~df.index.duplicated(keep="last")]


def veri(aralik="2y"):
    d = {s: fiyat_cek(s, aralik) for s in EVREN}
    # takvim = ETF işlem günleri; kripto (7/24, bazen eksik bar) bu takvime ileri doldurulur
    takvim = pd.DataFrame({s: d[s]["adj"] for s in EVREN if s not in KRIPTO}).dropna().index
    adj = pd.DataFrame({s: d[s]["adj"].reindex(takvim.union(d[s].index)).ffill().reindex(takvim) for s in EVREN}).dropna()
    cls = pd.DataFrame({s: d[s]["close"].reindex(takvim.union(d[s].index)).ffill().reindex(takvim) for s in EVREN}).dropna()
    # seans bitmeden çalışırsa bugünün yarım barını at (NY 16:30 öncesi)
    from zoneinfo import ZoneInfo
    ny = dt.datetime.now(ZoneInfo("America/New_York"))
    if ny.hour * 60 + ny.minute < 16 * 60 + 30:
        bugun = pd.Timestamp(ny.date())
        adj, cls = adj[adj.index < bugun], cls[cls.index < bugun]
    return adj, cls


def hedef_agirlik(adj: pd.DataFrame) -> dict:
    """Verilen tarihe kadarki veriyle hedef ağırlıkları hesaplar."""
    p = adj.iloc[-1]
    skor = sum(adj.iloc[-1] / adj.iloc[-1 - n] - 1 for n in (21, 63, 126, 252)) / 4
    sma = adj.iloc[-200:].mean()
    getiri = adj.pct_change().iloc[-60:]
    vol = getiri.std() * math.sqrt(252)

    uygun = [s for s in RISKLI if p[s] > sma[s] and skor[s] > 0]
    secilen = sorted(uygun, key=lambda s: skor[s], reverse=True)[:TOP_N]
    w = {}
    if secilen:
        iv = {s: 1 / vol[s] for s in secilen}
        top = sum(iv.values())
        for s in secilen:
            w[s] = iv[s] / top * len(secilen) / TOP_N
    kw = sum(w.get(s, 0) for s in KRIPTO)
    if kw > KRIPTO_MAX:
        for s in KRIPTO:
            if s in w:
                w[s] *= KRIPTO_MAX / kw
    bos = 1 - sum(w.values())
    if bos > 1e-9:
        savunma = "IEF" if (p["IEF"] > sma["IEF"] and skor["IEF"] > 0) else "BIL"
        w[savunma] = w.get(savunma, 0) + bos

    # volatilite hedefi (kovaryansla)
    semb = list(w)
    cov = getiri[semb].cov().values * 252
    wv = np.array([w[s] for s in semb])
    pvol = float(math.sqrt(wv @ cov @ wv))
    if pvol > VOL_HEDEF:
        k = VOL_HEDEF / pvol
        for s in semb:
            if s != "BIL":
                w[s] *= k
        w["BIL"] = w.get("BIL", 0) + (1 - sum(w.values()))
    tablo = pd.DataFrame({"skor": skor, "fiyat>SMA200": p > sma, "vol60": vol})
    return {k: round(v, 4) for k, v in w.items() if v > 1e-4}, tablo, pvol


def ayin_ilk_islem_gunu(gun: pd.Timestamp, index) -> bool:
    ayin = [d for d in index if d.year == gun.year and d.month == gun.month]
    return bool(ayin) and ayin[0] == gun
