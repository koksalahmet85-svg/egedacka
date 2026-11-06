"""Dolar bazlı simülasyon: 1000 $ başlangıç + ayda 1000 $ katkı, Midas ücreti 1,5 $/emir.
Politikaları karşılaştırır; para ağırlıklı getiri (IRR) ve ödenen toplam ücret raporlanır."""
import sys, copy
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np, pandas as pd
import portfolio_engine as pe

adj = pd.read_pickle(Path(__file__).with_name("uzun_fiyat.pkl"))
ret = adj.pct_change().fillna(0)
sma = adj.rolling(200).mean()
CFG = copy.deepcopy(pe.CONFIG); CFG["crypto"] = []
CASH = CFG["cash"]


def irr(flows):  # aylık akışlar -> yıllık IRR
    lo, hi = -0.99, 1.0
    for _ in range(200):
        mid = (lo + hi) / 2
        npv = sum(f / (1 + mid) ** i for i, f in enumerate(flows))
        lo, hi = (mid, hi) if npv > 0 else (lo, mid)
    return (1 + mid) ** 12 - 1


def sim(start, fee=1.5, min_order=10, band=0.05, rot_every=1, topk=None, monthly=1000.0):
    days = adj.index[(adj.index >= start)]
    h, cash, rot, cnt = {}, 0.0, {}, {}
    flows, fees, n_orders, m_i, month = [], 0.0, 0, 0, None

    def trade(t, usd):  # usd>0 al, <0 sat
        nonlocal cash, fees, n_orders
        h[t] = h.get(t, 0) + usd; cash -= usd + fee; fees += fee; n_orders += 1

    for g in days:
        r = ret.loc[g]
        for t in h: h[t] *= 1 + r[t]
        if g.month != month:
            month = g.month; cash += monthly; flows.append(-monthly)
            V = sum(h.values()) + cash
            new_rot = pe.target_weights(adj.loc[:g], CFG) if (m_i % rot_every == 0 or not rot) else rot
            changed = set(t for t in new_rot if t != CASH) != set(t for t in rot if t != CASH)
            rot = new_rot; tgt = pe.combine(rot, CFG); m_i += 1
            names = set(tgt) | set(t for t in h if h[t] > 1)
            drift = max(abs(tgt.get(t, 0) - h.get(t, 0) / V) for t in names)
            full = topk is None or changed or drift > band
            if full:
                deltas = {t: tgt.get(t, 0) * V - h.get(t, 0) for t in names}
                for t, d in sorted(deltas.items(), key=lambda x: x[1]):  # önce satış
                    must = (tgt.get(t, 0) == 0 and h.get(t, 0) > 1) or (h.get(t, 0) <= 1 and tgt.get(t, 0) > 0)
                    if abs(d) >= min_order and (abs(d) / V >= band or must or topk is None and abs(d) / V >= band):
                        if d > 0: d = min(d, cash - fee)
                        if abs(d) >= min_order: trade(t, d)
            # kalan nakit: en eksik k varlığa (k=None -> hepsine)
            V = sum(h.values()) + cash
            deficit = {t: tgt[t] * V - h.get(t, 0) for t in tgt if tgt[t] * V - h.get(t, 0) > 0}
            pick = sorted(deficit, key=deficit.get, reverse=True)[: (topk or len(deficit))]
            tot = sum(deficit[t] for t in pick)
            avail = cash - fee * len(pick)
            for t in pick:
                usd = min(deficit[t], avail * deficit[t] / tot) if tot > 0 else 0
                if usd >= min_order and cash - usd - fee >= 0: trade(t, usd)
        else:  # acil çıkış (yalnız uydu payı)
            tgt = pe.combine(rot, CFG)
            for t in [t for t in rot if t != CASH and h.get(t, 0) > 1]:
                cnt[t] = cnt.get(t, 0) + 1 if adj.at[g, t] < sma.at[g, t] else 0
                if cnt[t] >= 3:
                    cut = h[t] * (1 - CFG["core_weight"]) * rot[t] / tgt[t]
                    if cut >= min_order:
                        trade(t, -cut)
                        if cash - fee >= min_order: trade(CASH, cash - fee)
                    rot = {**{k: v for k, v in rot.items() if k != t}, CASH: rot.get(CASH, 0) + rot[t]}; cnt[t] = 0
    V = sum(h.values()) + cash
    flows[-1] += V
    return {"Son değer": V, "Yatırılan": -sum(f for f in flows[:-1]) + monthly, "IRR": irr(flows),
            "Ücret": fees, "Emir": n_orders, "Ücret/yatırılan": fees / (monthly * len(flows))}


POL = [("Ücretsiz referans (fee=0)", dict(fee=0.0)),
       ("P0 Mevcut: aylık tam, min 10$", dict()),
       ("P1 Aylık tam, min 50$", dict(min_order=50)),
       ("P2 Aylık, bant %10, min 100$", dict(min_order=100, band=0.10)),
       ("P3 Akıllı: katkı en eksik 2'ye, tam reb. sadece seçim değişir/bant %10", dict(min_order=50, band=0.10, topk=2)),
       ("P4 Çeyreklik rotasyon + akıllı katkı", dict(min_order=50, band=0.10, topk=2, rot_every=3))]
if __name__ == "__main__":
    for start in ["2008-07-01", "2016-01-01", "2021-01-01"]:
        print(f"\n## Başlangıç {start}")
        for name, kw in POL:
            r = sim(start, **kw)
            print(f"{name:66s} IRR {r['IRR']:6.2%} | Son {r['Son değer']:>10,.0f} $ | Ücret {r['Ücret']:>7,.0f} $ ({r['Ücret/yatırılan']:.2%}) | {r['Emir']} emir", flush=True)
