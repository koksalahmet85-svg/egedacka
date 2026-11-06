"""2007→bugün uzun veri seti: kısa geçmişli ETF'ler, kurucudan önce vekil getirilerle uzatılır.
  AVUV  <- VBR (Vanguard small-cap value)
  NTSX  <- 0.9×SPY + 0.6×(IEF − BIL)   (90/60 tanımı)
  DBMF  <- sentetik TSMOM (Moskowitz-Ooi-Pedersen 2012): 8 ETF, 12 ay işaret, ters vol, yıllık %0,85 ücret
  VEA   <- EFA ;  Kripto: yok (2014/2017 başlıyor)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import portfolio_engine as pe

TSMOM_EVREN = ["SPY", "EFA", "EEM", "IEF", "TLT", "GLD", "DBC", "UUP"]


def _ret(t, start):
    return pe.fetch_one(t, start=start)["adj"].pct_change()


def tsmom(r: pd.DataFrame, cash: pd.Series, fee=0.0085) -> pd.Series:
    month_end = r.index.to_series().groupby(r.index.to_period("M")).last()
    px = (1 + r.fillna(0)).cumprod()
    vol = r.rolling(60).std() * np.sqrt(252)
    w = pd.DataFrame(np.nan, index=r.index, columns=r.columns)
    for d in month_end:
        i = r.index.get_loc(d)
        if i < 252: continue
        sig = np.sign(px.iloc[i] / px.iloc[i - 252] - 1 - (1 + cash.iloc[i - 251:i + 1].fillna(0)).prod() + 1)
        w.loc[d] = sig * 0.40 / vol.iloc[i] / len(r.columns)
    w = w.ffill().shift(1).fillna(0)
    return (w * r.sub(cash, axis=0)).sum(axis=1) + cash - fee / 252


def uzun(start="2005-01-01") -> pd.DataFrame:
    tick = ["SPY", "QQQ", "VEA", "EFA", "VWO", "VBR", "AVUV", "NTSX", "DBMF", "GLD", "BIL", "IEF", "EEM", "TLT", "DBC", "UUP", "AQMIX"]
    R = pd.DataFrame({t: _ret(t, start) for t in tick}).dropna(subset=["SPY"])
    R["BIL"] = R["BIL"].fillna(0.0)
    ts = tsmom(R[TSMOM_EVREN].dropna(), R["BIL"])
    proxy = {"AVUV": R["VBR"], "NTSX": 0.9 * R["SPY"] + 0.6 * (R["IEF"] - R["BIL"]), "DBMF": ts, "VEA": R["EFA"]}
    out = pd.DataFrame(index=R.index)
    for t in ["SPY", "QQQ", "VEA", "VWO", "AVUV", "NTSX", "DBMF", "GLD", "BIL"]:
        s = R[t].copy()
        if t in proxy:
            first = s.first_valid_index()
            s.loc[:first] = proxy[t].loc[:first]
            s.loc[first] = R[t].loc[first] if not np.isnan(R[t].loc[first]) else proxy[t].loc[first]
        out[t] = s
    out = out.dropna()
    out = out[out.index >= "2006-06-01"]
    return (1 + out).cumprod() * 100, R, ts


if __name__ == "__main__":
    adj, R, ts = uzun()
    ov = pd.concat({"proxy": ts, "DBMF": R["DBMF"], "AQMIX": R["AQMIX"]}, axis=1).dropna()
    m = (1 + ov).resample("ME").prod() - 1
    print("Vekil doğrulama (aylık korelasyon, 2019-05→):"); print(m.corr().round(2))
    print("NTSX vekil korelasyon:", round(pd.concat([0.9*R.SPY+0.6*(R.IEF-R.BIL), R.NTSX],axis=1).dropna().corr().iloc[0,1],3),
          "| AVUV~VBR:", round(R[["AVUV","VBR"]].dropna().corr().iloc[0,1],3))
    y = (1 + pd.concat({"TSMOM vekil": ts, "SPY": R.SPY}, axis=1)).resample("YE").prod() - 1
    print((y.loc["2007":"2010"].round(3) * 100).to_string())
    adj.to_pickle(Path(__file__).with_name("uzun_fiyat.pkl"))
    print("kaydedildi", adj.index[0].date(), "->", adj.index[-1].date(), adj.shape)
