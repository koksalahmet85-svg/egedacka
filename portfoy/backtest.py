"""Basit günlük backtest: kurallar strateji.py ile birebir. Maliyet: işlem hacminin %0.10'u."""
import math, sys
import numpy as np, pandas as pd
from strateji import veri, hedef_agirlik, RISKLI, ESIK, GUNLUK_KURAL

MALIYET = 0.0010
adj, cls = veri("max")
adj = adj[adj.index >= "2007-06-01"]
ret = adj.pct_change().fillna(0)
sma200 = adj.rolling(200).mean()
gunler = adj.index[260:]

w = {"BIL": 1.0}; deger = 1.0; seri = []; alt_sayac = {}
onceki_ay = None
for i, g in enumerate(gunler):
    # günün getirisi (dünkü ağırlıklarla)
    deger *= 1 + sum(w.get(s, 0) * ret.at[g, s] for s in w)
    # ağırlıklar fiyatla kayar
    top = sum(w[s] * (1 + ret.at[g, s]) for s in w)
    w = {s: w[s] * (1 + ret.at[g, s]) / top for s in w}
    # sinyaller günün kapanışında, ertesi gün uygulanır (gün sonu kapanış varsayımı)
    yeni = None
    if onceki_ay != g.month:
        yeni, _, _ = hedef_agirlik(adj.loc[:g])
        onceki_ay = g.month
    elif GUNLUK_KURAL:
        for s in [s for s in w if s in RISKLI]:
            alt_sayac[s] = alt_sayac.get(s, 0) + 1 if adj.at[g, s] < sma200.at[g, s] else 0
            if alt_sayac[s] >= 3:
                yeni = dict(w); yeni["BIL"] = yeni.get("BIL", 0) + yeni.pop(s); alt_sayac[s] = 0
    if yeni:
        semb = set(w) | set(yeni)
        if max(abs(yeni.get(s, 0) - w.get(s, 0)) for s in semb) >= ESIK or set(yeni) != set(w):
            ciro = sum(abs(yeni.get(s, 0) - w.get(s, 0)) for s in semb)
            deger *= 1 - ciro * MALIYET
            w = yeni
    seri.append((g, deger))

s = pd.Series(dict(seri))
def ozet(x, ad):
    r = x.pct_change().dropna(); yil = len(r) / 252
    cagr = x.iloc[-1] ** (1 / yil) - 1 if x.iloc[0] == 1 else (x.iloc[-1] / x.iloc[0]) ** (1 / yil) - 1
    vol = r.std() * math.sqrt(252); sharpe = (r.mean() * 252) / vol
    mdd = (x / x.cummax() - 1).min()
    yillik = x.resample("YE").last().pct_change().dropna()
    print(f"{ad:12s} CAGR {cagr:6.1%} | Vol {vol:5.1%} | Sharpe {sharpe:4.2f} | MaxDD {mdd:6.1%} | en kötü yıl {yillik.min():6.1%}")
ozet(s, "Cloue")
spy = (1 + ret["SPY"].loc[gunler]).cumprod(); ozet(spy, "SPY al-tut")
k = 0.6 * ret["SPY"] + 0.4 * ret["IEF"]; ozet((1 + k.loc[gunler]).cumprod(), "60/40")
print("Dönem:", gunler[0].date(), "->", gunler[-1].date())
if 0: print(s.resample("YE").last().pct_change().fillna(s.resample("YE").last().iloc[0]-1).map("{:.1%}".format).to_string())
