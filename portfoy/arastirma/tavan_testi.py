"""BIST tavan (+%9,5 üstü kapanış) sonrası ertesi gün getirileri. Sadece araştırma."""
import sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import portfolio_engine as pe

T = """THYAO ASELS GARAN AKBNK YKBNK ISCTR KCHOL SAHOL TUPRS EREGL BIMAS SISE PETKM FROTO TOASO ARCLK TCELL TTKOM KOZAL KOZAA
PGSUS HEKTS SASA ODAS KONTR ALARK ENKAI TAVHL MGROS SOKM VESTL VESBE DOHOL EKGYO HALKB VAKBN TSKB ALBRK SKBNK QNBTR
GUBRF BAGFS AKSA KRDMD ISMEN OYAKC CIMSA AKCNS NUHCM BUCIM ULKER CCOLA AEFES TATGD KERVT PNSUT BANVT TUKAS PETUN
AGHOL GSDHO GLYHO NTHOL METRO ECILC ECZYT DEVA SELEC LKMNH MPARK EGEEN OTKAR TTRAK KARSN ASUZU DOAS BRISA GOODY
JANTS KORDS PARSN FMIZP EGSER KUTPO TRKCM ANACM SODA ZOREN AKSEN AYEN AYDEM GWIND ENJSA AKENR NATEN BIOEN ESEN
LOGO NETAS KAREL ARENA INDES DGATE LINK ARMDA ALCTL ESCOM KFEIN SMART PAPIL MAVI BOSSA YATAS DESA ADESE HEDEF GSRAY
FENER BJKAS TSPOR IPEKE ISGYO TRGYO SNGYO OZKGY ALGYO VKGYO AVGYO PSGYO KLGYO RYGYO DZGYO NUGYO PEKGY YGYO EUREN
QUAGR KMPUR KLKIM BRSAN BRYAT CEMTS CEMAS CUSAN DITAS DMSAS ERBOS IZMDC KRDMA KRDMB SARKY TUCLK BURCE BURVA CELHA""".split()

rows = []
for t in T:
    try:
        d = pe.fetch_one(t + ".IS", start="2015-01-01", retries=2)[["close"]]
    except Exception:
        continue
    o = pe._yahoo_direct  # açılış için ham API
    try:
        import json, urllib.request
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{t}.IS?period1=1420070400&period2={int(time.time())}&interval=1d"
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))["chart"]["result"][0]
        q = j["indicators"]["quote"][0]
        df = pd.DataFrame({"o": q["open"], "h": q["high"], "l": q["low"], "c": q["close"], "v": q["volume"]},
                          index=pd.to_datetime(j["timestamp"], unit="s").normalize()).dropna()
    except Exception:
        continue
    df = df[df.v > 0]
    r = df.c.pct_change()
    tavan = (r >= 0.095) & (df.c >= df.h * 0.999)          # gün tavanda kapanmış
    nxt = df.shift(-1)
    for dday in df.index[tavan.fillna(False)]:
        n = nxt.loc[dday]
        if np.isnan(n.c): continue
        i = df.index.get_loc(dday)
        c5 = df.c.iloc[i + 5] if i + 5 < len(df) else np.nan
        rows.append({"t": t, "d": dday, "gap": n.o / df.c.iloc[i] - 1, "oc": n.c / n.o - 1,
                     "cc": n.c / df.c.iloc[i] - 1, "c5": c5 / df.c.iloc[i] - 1,
                     "ertesi_tavan_acilis": n.o >= df.c.iloc[i] * 1.095})
R = pd.DataFrame(rows)
COST = 0.002  # gidiş-dönüş komisyon+spread (iyimser)
print(f"{R.t.nunique()} hisse, {len(R)} tavan günü, {R.d.min().date()}→{R.d.max().date()}")
print(f"Ertesi gün tavandan açılan (alım neredeyse imkânsız): {R.ertesi_tavan_acilis.mean():.1%}")
for col, ad in [("cc", "Tavan kapanışta al → ertesi kapanışta sat"), ("oc", "Ertesi açılışta al → aynı gün kapanışta sat"),
                ("c5", "Tavan kapanışta al → 5 gün sonra sat")]:
    x = R[col].dropna() - COST
    print(f"{ad:45s} ort {x.mean():+.2%} | medyan {x.median():+.2%} | kazanan {(x>0).mean():.0%} | en kötü %5 {x.quantile(.05):+.1%}")
# gerçekçi: tavan kapanışta alım ancak tavan bozulduysa dolar; tavanda kalanlar (ertesi tavan açılış) alınamaz
fill = R[~R.ertesi_tavan_acilis]
print(f"Ertesi gün tavanda açmayanlar (alınabilenler) – ertesi açılış→kapanış: ort {(fill.oc-COST).mean():+.2%}, kazanan {((fill.oc-COST)>0).mean():.0%}")
y = R.assign(y=R.d.dt.year).groupby("y").oc.agg(["count", "mean"])
print("Yıllara göre (ertesi açılış→kapanış):"); print((y.assign(mean=lambda z: (z["mean"]-COST).map('{:+.2%}'.format))).to_string())
