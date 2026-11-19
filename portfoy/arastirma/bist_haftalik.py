"""BIST: tavan profili + haftalık stratejiler (TL bazında, 146 hisse, 2015→). Sadece araştırma."""
import sys, json, time, urllib.request
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
from tavan_testi import T

def ohlcv(t):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}.IS?period1=1420070400&period2={int(time.time())}&interval=1d"
    j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))["chart"]["result"][0]
    q = j["indicators"]["quote"][0]
    df = pd.DataFrame({"c": q["close"], "h": q["high"], "v": q["volume"]}, index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna()
    return df[df.v > 0]

C, V, H = {}, {}, {}
for t in T:
    try:
        d = ohlcv(t); C[t], V[t], H[t] = d.c, d.v * d.c, d.h
    except Exception:
        pass
C, V, H = pd.DataFrame(C), pd.DataFrame(V), pd.DataFrame(H)
r = C.pct_change(fill_method=None)
tav = (r >= 0.095) & (C >= H * 0.999)

# 1) Tavan profili
adv = V.rolling(60).median().shift(1)               # tavan öncesi 60g medyan TL hacim
size_q = adv.rank(axis=1, pct=True)
prof = size_q[tav].stack()
print(f"Tavan günlerinin hacim çeyreklerine dağılımı (Q1=en düşük hacimli %25):")
print(pd.cut(prof, [0, .25, .5, .75, 1], labels=["Q1", "Q2", "Q3", "Q4"]).value_counts(normalize=True).sort_index().map("{:.0%}".format).to_string())
# seri tavanlar ve sonrası
streak = tav.astype(int).groupby((~tav).cumsum()).cumsum() if False else None
fwd20 = C.shift(-20) / C - 1
s3 = tav & tav.shift(1) & tav.shift(2)
print(f"\n3+ gün üst üste tavan sonrası 20 iş günü getirisi: medyan {fwd20[s3].stack().median():+.1%}, ort {fwd20[s3].stack().mean():+.1%}, "
      f"negatif oranı {(fwd20[s3].stack()<0).mean():.0%}, n={int(s3.sum().sum())}")
print(f"Tek tavan sonrası 20 gün: medyan {fwd20[tav & ~tav.shift(1).fillna(False)].stack().median():+.1%}")

# 2) Haftalık stratejiler (Cuma kapanış → sonraki Cuma kapanış)
W = C.resample("W-FRI").last(); wr = W.pct_change(fill_method=None)
wt = tav.resample("W-FRI").sum() > 0
COST = 0.004   # gidiş-dönüş: komisyon + spread (küçük hisselerde daha yüksek olabilir)
def run(sig):
    out = []
    for i in range(len(W) - 1):
        names = sig.iloc[i][sig.iloc[i]].index
        if len(names) == 0: out.append(0.0); continue
        out.append(wr.iloc[i + 1][names].mean() - COST)
    return pd.Series(out, index=W.index[1:]).fillna(0)
mom = (W.shift(1) / W.shift(26) - 1)                 # 6 ay, son hafta hariç
top = mom.rank(axis=1, ascending=False) <= 10
loser = wr.rank(axis=1) <= 10                         # geçen haftanın en çok düşen 10'u
ew = wr.shift(-1).mean(axis=1).iloc[:-1]
def st(x, ad):
    x = x.loc["2016":]; g = (1 + x).cumprod(); yrs = len(x) / 52
    print(f"{ad:42s} yıllık {g.iloc[-1]**(1/yrs)-1:+6.1%} | haftalık kazanma {(x>0).mean():.0%} | maxDD {(g/g.cummax()-1).min():+.0%}")
print("\nHaftalık stratejiler (TL, maliyet %0,4 gidiş-dönüş/hafta, 2016→):")
st(ew, "Eşit ağırlık tüm hisseler (al-tut, maliyetsiz)")
st(run(wt), "Geçen hafta tavan yapanları al, 1 hafta tut")
st(run(top), "6 ay momentum en iyi 10, haftalık yenile")
st(run(loser), "Geçen haftanın en çok düşen 10'u (dönüş)")
