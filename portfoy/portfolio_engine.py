"""
portfolio_engine.py — Cloue kural tabanlı ETF rotasyon motoru.

Mimari: ÇEKİRDEK + UYDU
  ÇEKİRDEK (%50, hep tutulur, aylık sabit ağırlığa dönülür):
     NTSX %60 (90/60 örtülü kaldıraç) · DBMF %20 (CTA / kriz alfası) · GLD %20
     Gerekçe: return stacking ve CTA'nın faydası SÜREKLİ tutulunca çıkar; momentum
     rotasyonuna sokulunca etkisi kayboluyor (backtest: Sharpe 1,00 vs 1,05 — fark yok).
  UYDU (%50, aşağıdaki kurallarla rotasyon):
Kurallar
  1. Momentum skoru  = 1, 3, 6, 12 aylık getirilerin aritmetik ortalaması.
  2. Trend filtresi  = kapanış > SMA_200 (BIL hariç tüm riskli varlıklar).
  3. Seçim           = filtreyi geçenlerden skoru en yüksek TOP_N (3); boş slot -> BIL.
  4. Ağırlık         = seçilenler arasında ters volatilite (60 günlük günlük getiri std).
  5. Rebalance       = ayda bir (ayın ilk işlem günü kapanışından sonra). Ağırlık farkı < %5 ise işlem yok.
  6. Acil çıkış      = eldeki riskli varlık 3 ardışık kapanış SMA_200 altında -> sat, BIL'e geç.
  7. Aylık katkı     = nakit > %5 ise yeni para eksik ağırlıklara dağıtılır, satış yapılmaz.

Durum `portfoy.json` dosyasında tutulur (birim/fon payı muhasebesi: katkılar getiri sayılmaz).

Kullanım
  python3 portfolio_engine.py                 # rapor üret, durumu kaydet, Telegram'a gönder
  python3 portfolio_engine.py --dry-run       # hiçbir şey kaydetme, Telegram'a gönderme
  python3 portfolio_engine.py --no-telegram   # kaydet ama mesaj atma
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import math
import os
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

log = logging.getLogger("cloue")
ROOT = Path(__file__).resolve().parent
STATE_FILE = ROOT / "portfoy.json"
REPORT_DIR = ROOT / "raporlar"

# ----------------------------------------------------------------------------- yapılandırma
CONFIG = {
    # Ana büyüme & faktör, örtülü kaldıraç, kriz alfası
    "core": {"NTSX": 0.60, "DBMF": 0.20, "GLD": 0.20},
    "core_weight": 0.50,          # 0 = sadece rotasyon (orijinal prompt)
    "risky": ["SPY", "QQQ", "VEA", "VWO", "AVUV", "NTSX", "DBMF", "GLD"],
    "crypto": ["BTC-USD", "ETH-USD"],   # [] = kripto yok
    "crypto_cap": 0.20,           # kripto toplam üst sınırı
    "cash": "BIL",
    "top_n": 3,
    "sma": 200,
    "vol_window": 60,
    "lookbacks": (21, 63, 126, 252),   # ≈ 1, 3, 6, 12 ay (işlem günü)
    "require_positive_score": False,   # True = çift momentum (skor > 0 şartı da)
    "rebalance_threshold": 0.05,
    "exit_days": 3,
    "min_order_usd": 10.0,
}


def universe(cfg=CONFIG) -> list[str]:
    return list(dict.fromkeys(list(cfg["core"]) + cfg["risky"] + cfg["crypto"] + [cfg["cash"]]))


# ----------------------------------------------------------------------------- veri
def _yahoo_direct(ticker: str, start: str | None, period: str) -> pd.DataFrame:
    """yfinance çalışmazsa yedek: Yahoo chart API'sine doğrudan istek."""
    if start:
        p1 = int(pd.Timestamp(start).timestamp())
        q = f"period1={p1}&period2={int(time.time())}"
    else:
        q = f"range={period}"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?{q}&interval=1d&events=div%2Csplit"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        j = json.load(r)["chart"]["result"][0]
    idx = pd.to_datetime(j["timestamp"], unit="s").normalize()
    df = pd.DataFrame({"adj": j["indicators"]["adjclose"][0]["adjclose"],
                       "close": j["indicators"]["quote"][0]["close"]}, index=idx).dropna()
    return df[~df.index.duplicated(keep="last")]


def _yfinance(ticker: str, start: str | None, period: str) -> pd.DataFrame:
    import yfinance as yf
    kw = {"start": start} if start else {"period": period}
    raw = yf.Ticker(ticker).history(auto_adjust=False, actions=False, **kw)
    if raw is None or raw.empty:
        raise ValueError(f"{ticker}: yfinance boş döndü")
    idx = pd.DatetimeIndex(raw.index).tz_localize(None).normalize()
    df = pd.DataFrame({"adj": raw["Adj Close"].values, "close": raw["Close"].values}, index=idx).dropna()
    return df[~df.index.duplicated(keep="last")]


def fetch_one(ticker: str, start: str | None = None, period: str = "2y", retries: int = 4) -> pd.DataFrame:
    """Önce yfinance, olmazsa doğrudan API; her biri üstel bekleme ile tekrar denenir."""
    last_err = None
    for attempt in range(retries):
        for fn in (_yfinance, _yahoo_direct):
            try:
                df = fn(ticker, start, period)
                if len(df) > 0:
                    return df
            except Exception as e:  # ağ kopması, rate limit, şema değişikliği…
                last_err = e
                log.warning("%s / %s denemesi %d başarısız: %s", ticker, fn.__name__, attempt + 1, e)
        time.sleep(2 ** attempt)
    raise RuntimeError(f"{ticker} verisi alınamadı: {last_err}")


def fetch_prices(cfg=CONFIG, start: str | None = None, period: str = "2y",
                 drop_partial: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Düzeltilmiş (adj) ve ham (close) kapanışlar; takvim = ETF işlem günleri."""
    data = {t: fetch_one(t, start, period) for t in universe(cfg)}
    etfs = [t for t in universe(cfg) if t not in cfg["crypto"]]
    cal = pd.concat([data[t]["adj"] for t in etfs], axis=1).dropna().index
    def align(col):
        return pd.DataFrame({t: data[t][col].reindex(cal.union(data[t].index)).ffill().reindex(cal)
                             for t in universe(cfg)}).dropna()
    adj, close = align("adj"), align("close")
    if drop_partial:  # seans bitmeden çalışırsa bugünün yarım barını at
        ny = dt.datetime.now(ZoneInfo("America/New_York"))
        if ny.hour * 60 + ny.minute < 16 * 60 + 30:
            today = pd.Timestamp(ny.date())
            adj, close = adj[adj.index < today], close[close.index < today]
    if len(adj) < max(cfg["lookbacks"]) + 1:
        raise RuntimeError(f"Yetersiz geçmiş: {len(adj)} gün")
    return adj, close


# ----------------------------------------------------------------------------- sinyal
def signals(adj: pd.DataFrame, cfg=CONFIG) -> pd.DataFrame:
    last = adj.iloc[-1]
    score = sum(last / adj.iloc[-1 - n] - 1 for n in cfg["lookbacks"]) / len(cfg["lookbacks"])
    sma = adj.iloc[-cfg["sma"]:].mean()
    vol = adj.pct_change().iloc[-cfg["vol_window"]:].std() * math.sqrt(252)
    return pd.DataFrame({"score": score, "above_sma": last > sma, "vol": vol})


def combine(rot: dict[str, float], cfg=CONFIG) -> dict[str, float]:
    """Toplam hedef = core_weight × çekirdek + (1 − core_weight) × rotasyon."""
    cw = cfg["core_weight"]
    out: dict[str, float] = {}
    for t, w in cfg["core"].items():
        out[t] = out.get(t, 0) + cw * w
    for t, w in rot.items():
        out[t] = out.get(t, 0) + (1 - cw) * w
    return {t: round(v, 4) for t, v in out.items() if v > 1e-4}


def target_weights(adj: pd.DataFrame, cfg=CONFIG) -> dict[str, float]:
    """UYDU (rotasyon) ağırlıkları; toplamı 1."""
    sig = signals(adj, cfg)
    pool = cfg["risky"] + cfg["crypto"]
    ok = [t for t in pool if sig.at[t, "above_sma"]
          and (sig.at[t, "score"] > 0 or not cfg["require_positive_score"])]
    picks = sorted(ok, key=lambda t: sig.at[t, "score"], reverse=True)[: cfg["top_n"]]
    w: dict[str, float] = {}
    if picks:
        inv = {t: 1 / sig.at[t, "vol"] for t in picks}
        tot = sum(inv.values())
        for t in picks:  # her dolu slot 1/top_n; seçilenler arasında ters volatilite
            w[t] = inv[t] / tot * len(picks) / cfg["top_n"]
    cw = sum(w.get(t, 0) for t in cfg["crypto"])
    if cw > cfg["crypto_cap"]:
        for t in cfg["crypto"]:
            if t in w:
                w[t] *= cfg["crypto_cap"] / cw
    w[cfg["cash"]] = w.get(cfg["cash"], 0) + max(0.0, 1 - sum(w.values()))
    return {t: round(v, 4) for t, v in w.items() if v > 1e-4}


# ----------------------------------------------------------------------------- durum
DEFAULT_STATE = {"rotasyon": {}, "rotasyon_aday": {}, "nakit": 0.0, "pozisyonlar": {}, "birim": 0.0, "yatirilan": 0.0,
                 "zirve_birim": 1.0, "son_dengeleme": None, "alt_sayac": {}, "son_sayac_gunu": None}


def load_state(path: Path = STATE_FILE) -> dict:
    try:
        st = json.loads(path.read_text())
    except FileNotFoundError:
        st = {}
    for k, v in DEFAULT_STATE.items():
        st.setdefault(k, v if not isinstance(v, dict) else dict(v))
    return st


def save_state(st: dict, path: Path = STATE_FILE) -> None:
    """Atomik yazım: yarım kalmış JSON ile durum bozulmaz."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(st, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


# ----------------------------------------------------------------------------- karar
def decide(st: dict, adj: pd.DataFrame, close: pd.DataFrame, cfg=CONFIG) -> dict:
    last_day = adj.index[-1]
    px = close.iloc[-1]
    sma = adj.iloc[-cfg["sma"]:].mean()
    pos = {t: a for t, a in st["pozisyonlar"].items() if a > 1e-9}
    value = st["nakit"] + sum(a * px[t] for t, a in pos.items())
    cur_w = {t: a * px[t] / value for t, a in pos.items()} if value > 0 else {}

    # acil çıkış yalnız UYDU pozisyonları için (çekirdek her koşulda tutulur)
    held_rot = {t: w for t, w in st.get("rotasyon", {}).items() if t != cfg["cash"] and t in pos}
    if st.get("son_sayac_gunu") != str(last_day.date()):
        for t in list(st["alt_sayac"]):
            if t not in held_rot:
                st["alt_sayac"].pop(t)
        for t in held_rot:
            below = adj[t].iloc[-1] < sma[t]
            st["alt_sayac"][t] = st["alt_sayac"].get(t, 0) + 1 if below else 0
        st["son_sayac_gunu"] = str(last_day.date())

    rot = target_weights(adj, cfg)
    target = combine(rot, cfg)
    reason, orders = None, []
    month_changed = st["son_dengeleme"] is None or st["son_dengeleme"][:7] != str(last_day.date())[:7]
    exits = [t for t in held_rot if st["alt_sayac"].get(t, 0) >= cfg["exit_days"]]

    if not pos and st["nakit"] > 0:
        reason = "BAŞLANGIÇ"
    elif month_changed:
        reason = "AYLIK REBALANCE"
    elif exits:
        reason = "ACİL ÇIKIŞ: " + ", ".join(exits) + f" {cfg['exit_days']} kapanıştır SMA200 altında"
        target = dict(cur_w)
        old_total = combine(st["rotasyon"], cfg)
        for t in exits:  # yalnız uydu payını sat: mevcut ağırlığın uydu oranı kadarı
            share = (1 - cfg["core_weight"]) * st["rotasyon"][t] / old_total[t]
            cut = cur_w[t] * share
            target[t] -= cut
            target[cfg["cash"]] = target.get(cfg["cash"], 0) + cut
            st["rotasyon"][cfg["cash"]] = st["rotasyon"].get(cfg["cash"], 0) + st["rotasyon"].pop(t)
        target[cfg["cash"]] = target.get(cfg["cash"], 0) + st["nakit"] / value
    elif value > 0 and st["nakit"] / value > cfg["rebalance_threshold"]:
        reason = "KATKI"

    if reason == "KATKI":
        gap = {t: max(0.0, w * value - pos.get(t, 0) * px[t]) for t, w in target.items()}
        tot = sum(gap.values()) or 1.0
        for t, g in gap.items():
            usd = g / tot * st["nakit"]
            if usd >= cfg["min_order_usd"]:
                orders.append({"side": "AL", "ticker": t, "qty": usd / px[t], "price": float(px[t]), "usd": usd})
    elif reason:
        names = set(target) | set(pos)
        drift = max(abs(target.get(t, 0) - cur_w.get(t, 0)) for t in names)
        if reason == "AYLIK REBALANCE" and drift < cfg["rebalance_threshold"] and set(target) == set(pos):
            reason += " (fark < %5, işlem yok)"
            st["son_dengeleme"], st["rotasyon"] = str(last_day.date()), rot
        else:
            for t in sorted(names, key=lambda t: target.get(t, 0) - cur_w.get(t, 0)):  # önce satışlar
                delta = target.get(t, 0) * value / px[t] - pos.get(t, 0)
                if abs(delta * px[t]) >= cfg["min_order_usd"]:
                    orders.append({"side": "SAT" if delta < 0 else "AL", "ticker": t, "qty": abs(delta),
                                   "price": float(px[t]), "usd": abs(delta) * px[t]})

    if reason and (reason.startswith("BAŞLANGIÇ") or reason.startswith("AYLIK")):
        st["rotasyon_aday"] = rot   # emirler gerçekleşince islem.py --dengeleme ile kalıcılaşır
    unit = value / st["birim"] if st["birim"] else 1.0
    st["zirve_birim"] = max(st.get("zirve_birim", 1.0), unit)
    return {"date": str(last_day.date()), "value": value, "invested": st["yatirilan"], "unit": unit,
            "ret": unit - 1, "dd": unit / st["zirve_birim"] - 1, "reason": reason, "orders": orders,
            "target": target, "current": cur_w, "cash": st["nakit"], "positions": pos, "prices": px,
            "signals": signals(adj, cfg), "rotation": rot, "counters": dict(st["alt_sayac"])}


# ----------------------------------------------------------------------------- rapor
def format_report(r: dict, cfg=CONFIG) -> str:
    L = [f"Cloue Portföy · son kapanış {r['date']}",
         f"Değer {r['value']:,.2f} $ · Yatırılan {r['invested']:,.0f} $ · Getiri {r['ret']:+.2%} · Zirveden {r['dd']:.2%}", ""]
    if r["orders"]:
        L.append(f"⚠️ İŞLEM GÜNÜ — {r['reason']}")
        L.append("Önce satışlar. ABD seansı 17:30 TSİ; ~15 dk sonra limit emir (alış +%0,2 / satış −%0,2):")
        for o in r["orders"]:
            L.append(f"  {o['side']:3s} {o['ticker']:5s} {o['qty']:.3f} adet @ {o['price']:.2f} ≈ {o['usd']:,.2f} $")
        L.append("Gerçekleşen adet/fiyatları Cloue'ya yaz.")
    else:
        L.append(f"✅ İşlem yok{(' — ' + r['reason']) if r['reason'] else ''}")
    L += ["", f"Çekirdek %{cfg['core_weight']*100:.0f}: " + ", ".join(f"{t} {w:.0%}" for t, w in cfg["core"].items()),
          "Uydu (rotasyon): " + ", ".join(f"{t} {w:.0%}" for t, w in sorted(r["rotation"].items(), key=lambda x: -x[1]))]
    L += ["Toplam hedef: " + ", ".join(f"{t} {w:.0%}" for t, w in sorted(r["target"].items(), key=lambda x: -x[1]))]
    if r["positions"]:
        L.append("Pozisyonlar: " + ", ".join(
            f"{t} {r['current'].get(t, 0):.0%}" + (f" (SMA altı {r['counters'].get(t, 0)}/{cfg['exit_days']})"
                                                   if r['counters'].get(t, 0) else "")
            for t in r["positions"]))
    s = r["signals"].drop(index=cfg["cash"]).sort_values("score", ascending=False)
    L += ["", "Sinyal (skor · trend · vol60):"]
    L += [f"  {t:7s} {row.score:+6.1%} {'↑' if row.above_sma else '↓'} {row.vol:5.1%}" for t, row in s.iterrows()]
    return "\n".join(L)


# ----------------------------------------------------------------------------- giriş noktası
def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-telegram", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    send = (lambda m: None)
    if not (a.dry_run or a.no_telegram):
        from telegram_notifier import send_message
        send = send_message
    try:
        st = load_state()
        adj, close = fetch_prices()
        r = decide(st, adj, close)
        text = format_report(r)
    except Exception as e:
        log.exception("Çalışma başarısız")
        send(f"❌ Cloue motoru hata verdi, rapor üretilemedi: {type(e).__name__}: {e}")
        return 1
    print(text)
    if not a.dry_run:
        save_state(st)
        REPORT_DIR.mkdir(exist_ok=True)
        (REPORT_DIR / f"{dt.date.today()}.md").write_text("```\n" + text + "\n```\n")
        send(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
