"""Günlük stratejiler × çok piyasa × ücret modeli. 500 $ hesap. Sadece araştırma."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import portfolio_engine as pe

ASSETS = {"SPY": "ABD hisse", "QQQ": "Nasdaq", "IWM": "ABD küçük", "EFA": "Gelişmiş (Avrupa+Japonya)", "EWG": "Almanya",
          "EWJ": "Japonya", "EEM": "Gelişen", "TLT": "ABD uzun tahvil", "GLD": "Altın", "SLV": "Gümüş",
          "USO": "Petrol", "DBA": "Tarım", "DBC": "Emtia sepeti", "UNG": "Doğalgaz", "BTC-USD": "Bitcoin"}
FEES = {"Midas 1,5$/emir": ("fix", 1.5), "IBKR ~1$/emir": ("fix", 1.0), "Yüzde %0,05 (vadeli/kripto borsa)": ("pct", 0.0005)}
bil = pe.fetch_one("BIL", start="2007-06-01")["adj"]

def rsi2(s):
    r = s.diff(); up = r.clip(lower=0).ewm(alpha=.5).mean(); dn = (-r.clip(upper=0)).ewm(alpha=.5).mean()
    return 100 - 100 / (1 + up / dn)

def sim(px, entry, exit_, fee):
    kind, f = fee
    cash, sh, inpos, n, vals = 500.0, 0.0, False, 0, []
    b = bil.reindex(px.index).ffill().bfill()
    for i in range(1, len(px)):
        p = px.iloc[i]
        if not inpos:
            cash *= b.iloc[i] / b.iloc[i - 1]
            if entry.iloc[i]:
                c = f if kind == "fix" else cash * f
                sh = (cash - c) / p; cash = 0; inpos = True; n += 1
        elif exit_.iloc[i]:
            v = sh * p; c = f if kind == "fix" else v * f
            cash = v - c; sh = 0; inpos = False
        vals.append(cash + sh * p)
    v = pd.Series(vals, index=px.index[1:]); y = len(v) / 252
    return (v.iloc[-1] / 500) ** (1 / y) - 1, (v / v.cummax() - 1).min(), n / y

rows = []
for t, ad in ASSETS.items():
    px = pe.fetch_one(t, start="2007-06-01")["adj"]
    if t.endswith("-USD"):  # kripto: işlem günleri ETF takvimi değil, 7/24; aynı kurallar
        pass
    px = px[px.index >= "2008-01-01"]
    sma200, sma5, sma20 = px.rolling(200).mean(), px.rolling(5).mean(), px.rolling(20).mean()
    r = rsi2(px)
    strategies = {"RSI(2) dönüş": ((r < 10) & (px > sma200), px > sma5),
                  "20g trend": (px > sma20, px < sma20)}
    bh = (px.iloc[-1] / px.iloc[200]) ** (252 / (len(px) - 200)) - 1
    for sname, (en, ex) in strategies.items():
        res = {}
        for fname, fee in FEES.items():
            c, dd, tpy = sim(px.iloc[200:], en.iloc[200:], ex.iloc[200:], fee)
            res[fname] = c
        rows.append({"Varlık": f"{t} ({ad})", "Strateji": sname, "Al-tut": bh, **res, "MaxDD(%0,05)": dd, "İşlem/yıl": tpy})
R = pd.DataFrame(rows)
b = bil[bil.index >= "2008-10-01"]; bil_c = (b.iloc[-1] / b.iloc[0]) ** (252 / len(b)) - 1
pd.set_option("display.width", 250)
fmt = R.copy()
for c in ["Al-tut", *FEES, "MaxDD(%0,05)"]: fmt[c] = fmt[c].map("{:+.1%}".format)
fmt["İşlem/yıl"] = fmt["İşlem/yıl"].map("{:.0f}".format)
print(fmt.to_string(index=False))
print(f"\nBIL (referans, 2008→): yıllık {bil_c:+.1%}")
for f in FEES:
    beat = R[R[f] > bil_c]; beat_bh = R[(R[f] > bil_c) & (R[f] > R["Al-tut"])]
    print(f"{f:34s}: {len(beat)}/{len(R)} kombinasyon BIL'i geçti; hem BIL'i hem al-tut'u geçen: {len(beat_bh)}")
R.to_csv(Path(__file__).with_name("coklu_piyasa_sonuc.csv"), index=False)
