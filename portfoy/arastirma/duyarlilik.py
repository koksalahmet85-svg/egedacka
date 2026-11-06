"""Parametre duyarlılığı (tek seferde bir parametre). Amaç en iyiyi SEÇMEK değil, platoyu görmek."""
import sys, copy, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
import portfolio_engine as pe
from backtest import run, stats

adj = pd.read_pickle(Path(__file__).with_name("uzun_fiyat.pkl"))
ret = adj.pct_change().fillna(0)
BASE = copy.deepcopy(pe.CONFIG); BASE["crypto"] = []


def core_series(cfg, idx):
    w = dict(cfg["core"]); m = None; c = [1.0]
    for g in idx[1:]:
        r = ret.loc[g]; gr = sum(w[t] * (1 + r[t]) for t in w); c.append(c[-1] * gr)
        w = {t: w[t] * (1 + r[t]) / gr for t in w}
        if g.month != m: m = g.month; w = dict(cfg["core"])
    return pd.Series(c, index=idx)


def blend(sat, core, cw):
    # sleeve'ler arası aylık yeniden dengeleme
    rs, rc = sat.pct_change().fillna(0), core.pct_change().fillna(0)
    v, ws, out, m = 1.0, 1 - cw, [], None
    for g in sat.index:
        if g.month != m: m = g.month; ws = 1 - cw
        gr = ws * (1 + rs[g]) + (1 - ws) * (1 + rc[g]); v *= gr
        ws = ws * (1 + rs[g]) / gr; out.append(v)
    return pd.Series(out, index=sat.index)


def evaluate(cfg, exit_rule=True):
    sat, _ = run(cfg, None, adj=adj, exit_rule=exit_rule)
    if cfg["core_weight"] == 0: return sat
    core = core_series(cfg, sat.index)
    return sat if cfg["core_weight"] == 0 else (core if cfg["core_weight"] == 1 else blend(sat, core, cfg["core_weight"]))


def fmt(name, s):
    return (f"{name:34s} CAGR {s['CAGR']:6.1%} Vol {s['Vol']:5.1%} Sharpe {s['Sharpe']:4.2f} "
            f"MaxDD {s['MaxDD']:6.1%}")


variants = [("BAZ (canlı ayar)", {}, True),
            ("top_n=2", {"top_n": 2}, True), ("top_n=4", {"top_n": 4}, True),
            ("SMA 150", {"sma": 150}, True), ("SMA 250", {"sma": 250}, True),
            ("Lookback 3/6/12", {"lookbacks": (63, 126, 252)}, True),
            ("Lookback 12 ay", {"lookbacks": (252,)}, True),
            ("Skor>0 şartı", {"require_positive_score": True}, True),
            ("Acil çıkış KAPALI", {}, False),
            ("Çekirdek %0 (sadece uydu)", {"core_weight": 0.0}, True),
            ("Çekirdek %30", {"core_weight": 0.3}, True),
            ("Çekirdek %70", {"core_weight": 0.7}, True),
            ("Çekirdek %100 (sadece çekirdek)", {"core_weight": 1.0}, True)]
res = {}
for name, ch, ex in variants:
    cfg = copy.deepcopy(BASE); cfg.update(ch)
    s = evaluate(cfg, ex); res[name] = s
    print(fmt(name, stats(s)), flush=True)
idx = res["BAZ (canlı ayar)"].index
spy = (1 + ret["SPY"].loc[idx]).cumprod(); print(fmt("SPY al-tut", stats(spy)))
b6040 = blend((1 + ret["SPY"].loc[idx]).cumprod(), (1 + (ret["NTSX"].loc[idx] - 0.9 * ret["SPY"].loc[idx]) / 0.6 + ret["BIL"].loc[idx]).cumprod(), 0.4)
print("Dönem:", idx[0].date(), "->", idx[-1].date())
print("\nAlt dönemler (BAZ vs SPY):")
for a, b in [("2008", "2012"), ("2013", "2019"), ("2020", "2026")]:
    x = res["BAZ (canlı ayar)"].loc[a:b]; y = spy.loc[a:b]
    print(f"  {a}-{b}: Cloue {fmt('', stats(x))[35:]} | SPY CAGR {stats(y)['CAGR']:.1%} MaxDD {stats(y)['MaxDD']:.1%}")
pd.DataFrame(res).to_pickle(Path(__file__).with_name("duyarlilik.pkl"))
