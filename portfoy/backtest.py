"""Günlük backtest — portfolio_engine kurallarıyla birebir (target_weights + acil çıkış).

Varsayımlar: sinyal kapanışta, işlem aynı kapanışta; maliyet = ciro × %0,10.
Kullanım: python3 backtest.py --start 2019-09-26 --crypto --core 0.5   (canlı sistemin ayarı)
"""
import argparse, copy, math
import numpy as np, pandas as pd
import portfolio_engine as pe

COST = 0.0010


def run(cfg, start):
    adj, _ = pe.fetch_prices(cfg, start=start, drop_partial=False)
    ret = adj.pct_change().fillna(0)
    sma = adj.rolling(cfg["sma"]).mean()
    days = adj.index[max(cfg["lookbacks"]) + 1:]
    cash = cfg["cash"]
    w, nav, out, cnt, month = {cash: 1.0}, 1.0, [], {}, None
    for g in days:
        r = ret.loc[g]
        gross = sum(w[t] * (1 + r[t]) for t in w)
        nav *= gross
        w = {t: w[t] * (1 + r[t]) / gross for t in w}
        new = None
        if g.month != month:
            new, month = pe.target_weights(adj.loc[:g], cfg), g.month
        else:
            for t in [t for t in w if t != cash]:
                cnt[t] = cnt.get(t, 0) + 1 if adj.at[g, t] < sma.at[g, t] else 0
                if cnt[t] >= cfg["exit_days"]:
                    new = dict(w); new[cash] = new.get(cash, 0) + new.pop(t); cnt[t] = 0
        if new:
            names = set(w) | set(new)
            if set(new) != set(w) or max(abs(new.get(t, 0) - w.get(t, 0)) for t in names) >= cfg["rebalance_threshold"]:
                nav *= 1 - COST * sum(abs(new.get(t, 0) - w.get(t, 0)) for t in names)
                w = new
        out.append((g, nav))
    return pd.Series(dict(out)), ret.loc[days]


def stats(x):
    r = x.pct_change().dropna(); yrs = len(r) / 252
    return {"CAGR": (x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1, "Vol": r.std() * math.sqrt(252),
            "Sharpe": r.mean() * 252 / (r.std() * math.sqrt(252)), "MaxDD": (x / x.cummax() - 1).min()}


def line(name, s):
    return f"{name:28s} CAGR {s['CAGR']:6.1%} | Vol {s['Vol']:5.1%} | Sharpe {s['Sharpe']:4.2f} | MaxDD {s['MaxDD']:6.1%}"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2007-06-01")
    ap.add_argument("--crypto", action="store_true")
    ap.add_argument("--positive-score", action="store_true")
    ap.add_argument("--risky")
    ap.add_argument("--core", type=float, default=0.0, help="çekirdek ağırlığı (ör. 0.5); sleeve'ler ayrı simüle edilip karıştırılır")
    a = ap.parse_args()
    cfg = copy.deepcopy(pe.CONFIG)
    cfg["crypto"] = ["BTC-USD", "ETH-USD"] if a.crypto else []
    cfg["core"] = cfg["core"] if a.core else {}
    if a.positive_score: cfg["require_positive_score"] = True
    if a.risky: cfg["risky"] = a.risky.split(",")
    if "SPY" not in pe.universe(cfg): cfg["risky"].append("SPY")
    nav, ret = run(cfg, a.start)
    if a.core:
        w = dict(cfg["core"]); m = None; c = [1.0]
        for g in ret.index[1:]:
            r = ret.loc[g]; gr = sum(w[t] * (1 + r[t]) for t in w); c.append(c[-1] * gr)
            w = {t: w[t] * (1 + r[t]) / gr for t in w}
            if g.month != m: m = g.month; w = dict(cfg["core"])
        core = pd.Series(c, index=ret.index)
        print(line("Uydu (rotasyon)", stats(nav)))
        print(line("Çekirdek", stats(core)))
        nav = (a.core * core.pct_change().fillna(0) + (1 - a.core) * nav.pct_change().fillna(0) + 1).cumprod()
    print(line("Cloue", stats(nav)))
    print(line("SPY al-tut", stats((1 + ret["SPY"]).cumprod())))
    print("Dönem:", nav.index[0].date(), "->", nav.index[-1].date())
