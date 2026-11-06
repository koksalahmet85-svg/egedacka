"""Sentetik fiyatlarla kural testleri: python3 -m pytest -q tests  (ya da python3 tests/test_engine.py)"""
import copy, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import portfolio_engine as pe

CFG = copy.deepcopy(pe.CONFIG); CFG["crypto"] = []


def prices(n=300, trend=None, crash=None):
    idx = pd.bdate_range("2025-01-01", periods=n)
    rng = np.random.default_rng(0)
    df = {}
    for t in pe.universe(CFG):
        mu = (trend or {}).get(t, 0.0003)
        r = rng.normal(mu, 0.01, n)
        df[t] = 100 * np.cumprod(1 + r)
    adj = pd.DataFrame(df, index=idx)
    if crash:  # son günlerde sert düşüş
        adj.loc[adj.index[-5:], crash] *= 0.5
    return adj


def state(**kw):
    st = copy.deepcopy(pe.DEFAULT_STATE); st.update(birim=1000.0, yatirilan=1000.0, nakit=1000.0); st.update(kw)
    return st


def test_weights_sum_to_one():
    w = pe.combine(pe.target_weights(prices(), CFG), CFG)
    assert abs(sum(w.values()) - 1) < 1e-3


def test_all_below_sma_means_all_cash_in_satellite():
    adj = prices(trend={t: -0.003 for t in CFG["risky"]})
    assert pe.target_weights(adj, CFG) == {"BIL": 1.0}


def test_initial_orders_spend_cash():
    adj = prices(); r = pe.decide(state(), adj, adj, CFG)
    assert r["reason"] == "BAŞLANGIÇ" and abs(sum(o["usd"] for o in r["orders"]) - 1000) < 1


def test_contribution_buys_only():
    adj = prices(); px = adj.iloc[-1]
    rot = pe.target_weights(adj, CFG); tgt = pe.combine(rot, CFG)
    pos = {t: w * 1000 / px[t] for t, w in tgt.items()}
    st = state(nakit=1000.0, pozisyonlar=pos, rotasyon=rot, son_dengeleme=str(adj.index[-1].date()))
    r = pe.decide(st, adj, adj, CFG)
    assert r["reason"] == "KATKI" and all(o["side"] == "AL" for o in r["orders"])


def test_emergency_exit_sells_only_satellite_part():
    adj = prices(trend={"VEA": 0.002}, crash="VEA"); px = adj.iloc[-1]
    rot = {"VEA": 1 / 3, "BIL": 2 / 3}; tgt = pe.combine(rot, CFG)
    pos = {t: w * 1000 / px[t] for t, w in tgt.items()}
    st = state(nakit=0.0, pozisyonlar=pos, rotasyon=rot, son_dengeleme=str(adj.index[-1].date()),
               alt_sayac={"VEA": 2}, son_sayac_gunu="2000-01-01")
    r = pe.decide(st, adj, adj, CFG)
    assert r["reason"].startswith("ACİL ÇIKIŞ")
    sells = [o for o in r["orders"] if o["side"] == "SAT"]
    assert [o["ticker"] for o in sells] == ["VEA"]


def test_core_never_exits():
    adj = prices(crash="NTSX"); px = adj.iloc[-1]
    rot = {"BIL": 1.0}; tgt = pe.combine(rot, CFG)
    pos = {t: w * 1000 / px[t] for t, w in tgt.items()}
    st = state(nakit=0.0, pozisyonlar=pos, rotasyon=rot, son_dengeleme=str(adj.index[-1].date()),
               alt_sayac={"NTSX": 5}, son_sayac_gunu="2000-01-01")
    r = pe.decide(st, adj, adj, CFG)
    assert not r["orders"]




def test_monthly_same_picks_buys_only_topk():
    adj = prices(); px = adj.iloc[-1]
    rot = pe.target_weights(adj, CFG); tgt = pe.combine(rot, CFG)
    pos = {t: w * 1000 / px[t] for t, w in tgt.items()}
    st = state(nakit=1000.0, pozisyonlar=pos, rotasyon=rot, son_dengeleme="2000-01-01")
    r = pe.decide(st, adj, adj, CFG)
    assert r["reason"].startswith("KATKI") and len(r["orders"]) <= CFG["contribution_topk"]
    assert all(o["side"] == "AL" for o in r["orders"])


def test_monthly_changed_picks_full_rebalance():
    adj = prices(); px = adj.iloc[-1]
    rot = {"VWO": 1.0}; tgt = pe.combine(rot, CFG)
    pos = {t: w * 1000 / px[t] for t, w in tgt.items()}
    st = state(nakit=0.0, pozisyonlar=pos, rotasyon=rot, son_dengeleme="2000-01-01")
    r = pe.decide(st, adj, adj, CFG)
    assert r["reason"] == "AYLIK REBALANCE" and any(o["side"] == "SAT" for o in r["orders"])


def test_stale_data_rejected():
    adj = prices()
    try:
        pe.check_data(adj, {}, CFG); assert False, "bayat veri kabul edildi"
    except pe.DataQualityError:
        pass


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f(); print("OK", n)
