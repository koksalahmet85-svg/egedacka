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
    "rebalance_threshold": 0.10,       # tam rebalance yalnız seçim değişirse ya da sapma > %10
    "contribution_topk": 2,            # katkı/nakit en eksik 2 varlığa (Midas 1,5 $/emir: emir sayısını azaltır)
    "data_max_staleness_days": 4,      # son ETF verisi bundan eskiyse rapor üretme
    "data_max_daily_move": 0.25,       # ETF'de tek günde > %25 hareket = veri hatası şüphesi
    "exit_days": 3,
    "min_order_usd": 50.0,
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


def _crypto_hourly_fill(ticker: str, days: list[pd.Timestamp]) -> dict[pd.Timestamp, float]:
    """Yahoo günlük kripto barı eksikse: o günün 16:00 ET (ABD kapanışı) saatlik fiyatını kullan."""
    out: dict[pd.Timestamp, float] = {}
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=1mo&interval=60m"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            j = json.load(r)["chart"]["result"][0]
        ts = pd.to_datetime(j["timestamp"], unit="s", utc=True).tz_convert("America/New_York")
        s = pd.Series(j["indicators"]["quote"][0]["close"], index=ts).dropna()
        for d in days:
            cut = pd.Timestamp(d.date()).tz_localize("America/New_York") + pd.Timedelta(hours=16)
            w = s[(s.index <= cut) & (s.index > cut - pd.Timedelta(hours=6))]
            if len(w):
                out[d] = float(w.iloc[-1])
    except Exception as e:
        log.warning("%s saatlik doldurma başarısız: %s", ticker, e)
    return out


class DataQualityError(RuntimeError):
    pass


def check_data(adj: pd.DataFrame, raw: dict, cfg=CONFIG) -> None:
    """Bayat veya bozuk veriyle karar üretme: hata fırlat, Telegram'a uyarı gitsin."""
    last = adj.index[-1]
    age = (pd.Timestamp(dt.datetime.now(ZoneInfo("America/New_York")).date()) - last).days
    if age > cfg["data_max_staleness_days"]:
        raise DataQualityError(f"Son ortak kapanış {last.date()} ({age} gün eski)")
    etfs = [t for t in adj.columns if t not in cfg["crypto"]]
    jump = adj[etfs].pct_change().iloc[-5:].abs().max()
    bad = jump[jump > cfg["data_max_daily_move"]]
    if len(bad):
        raise DataQualityError("Şüpheli günlük hareket: " + ", ".join(f"{t} {v:.0%}" for t, v in bad.items()))
    for t in cfg["crypto"]:
        if raw[t].index[-1] < last - pd.Timedelta(days=3):
            raise DataQualityError(f"{t} verisi bayat: {raw[t].index[-1].date()}")


def fetch_prices(cfg=CONFIG, start: str | None = None, period: str = "2y",
                 drop_partial: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Düzeltilmiş (adj) ve ham (close) kapanışlar; takvim = ETF işlem günleri."""
    data = {t: fetch_one(t, start, period) for t in universe(cfg)}
    etfs = [t for t in universe(cfg) if t not in cfg["crypto"]]
    cal = pd.concat([data[t]["adj"] for t in etfs], axis=1).dropna().index
    for t in cfg["crypto"]:  # son 20 işlem gününde eksik kripto barlarını saatlik veriyle tamamla
        missing = [d for d in cal[-20:] if d not in data[t].index]
        if missing:
            fill = _crypto_hourly_fill(t, missing)
            log.info("%s eksik gün %s -> saatlikten doldurulan %d", t, [str(d.date()) for d in missing], len(fill))
            if fill:
                add = pd.DataFrame({"adj": fill, "close": fill})
                data[t] = pd.concat([data[t], add]).sort_index()
    def align(col):
        return pd.DataFrame({t: data[t][col].reindex(cal.union(data[t].index)).ffill().reindex(cal)
                             for t in universe(cfg)}).dropna()
    adj, close = align("adj"), align("close")
    if drop_partial:  # seans bitmeden çalışırsa bugünün yarım barını at
        ny = dt.datetime.now(ZoneInfo("America/New_York"))
        if ny.hour * 60 + ny.minute < 16 * 60 + 30:
            today = pd.Timestamp(ny.date())
            adj, close = adj[adj.index < today], close[close.index < today]
    check_data(adj, data, cfg)
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
    elif value > 0 and st["nakit"] >= cfg["min_order_usd"]:
        reason = "KATKI"

    if reason == "AYLIK REBALANCE":
        # Seçim aynı ve sapma bant içindeyse tam rebalance yok; yalnız nakit/katkı yerleştirilir.
        picks_old = {t for t in st.get("rotasyon", {}) if t != cfg["cash"]}
        picks_new = {t for t in rot if t != cfg["cash"]}
        inv = value - st["nakit"]  # sapma, nakit hariç yatırılmış kısım üzerinden ölçülür
        inv_w = {t: a * px[t] / inv for t, a in pos.items()} if inv > 0 else {}
        drift = max(abs(target.get(t, 0) - inv_w.get(t, 0)) for t in set(target) | set(pos))
        if picks_old == picks_new and drift <= cfg["rebalance_threshold"]:
            st["son_dengeleme"], st["rotasyon"] = str(last_day.date()), rot
            reason = (f"AYLIK — seçim değişmedi, sapma %{drift*100:.0f} ≤ %{cfg['rebalance_threshold']*100:.0f}"
                      + ("; nakit yerleştiriliyor" if st["nakit"] >= cfg["min_order_usd"] else "; işlem yok"))
            if st["nakit"] >= cfg["min_order_usd"]:
                reason = "KATKI · " + reason

    if reason and reason.startswith("KATKI"):
        gap = {t: w * value - pos.get(t, 0) * px[t] for t, w in target.items()}
        gap = {t: g for t, g in gap.items() if g > 0}
        pick = sorted(gap, key=gap.get, reverse=True)[: cfg["contribution_topk"]]
        tot = sum(gap[t] for t in pick) or 1.0
        for t in pick:
            usd = min(gap[t], st["nakit"] * gap[t] / tot) if len(pick) > 1 else st["nakit"]
            if usd >= cfg["min_order_usd"]:
                orders.append({"side": "AL", "ticker": t, "qty": usd / px[t], "price": float(px[t]), "usd": usd})
    elif reason and not reason.startswith("AYLIK —"):
        names = set(target) | set(pos)
        for t in sorted(names, key=lambda t: target.get(t, 0) - cur_w.get(t, 0)):  # önce satışlar
            delta = target.get(t, 0) * value / px[t] - pos.get(t, 0)
            if abs(delta * px[t]) >= cfg["min_order_usd"]:
                orders.append({"side": "SAT" if delta < 0 else "AL", "ticker": t, "qty": abs(delta),
                               "price": float(px[t]), "usd": abs(delta) * px[t]})

    if reason and (reason.startswith("BAŞLANGIÇ") or reason == "AYLIK REBALANCE"):
        st["rotasyon_aday"] = rot   # emirler gerçekleşince islem.py --dengeleme ile kalıcılaşır
    unit = value / st["birim"] if st["birim"] else 1.0
    st["zirve_birim"] = max(st.get("zirve_birim", 1.0), unit)
    return {"date": str(last_day.date()), "value": value, "invested": st["yatirilan"], "unit": unit,
            "ret": unit - 1, "dd": unit / st["zirve_birim"] - 1, "reason": reason, "orders": orders,
            "target": target, "current": cur_w, "cash": st["nakit"], "positions": pos, "prices": px,
            "signals": signals(adj, cfg), "rotation": rot, "counters": dict(st["alt_sayac"])}


# ----------------------------------------------------------------------------- rapor
# ----------------------------------------------------------------------------- piyasa bağlamı (ekonomist)
def market_context() -> dict | None:
    """Bilgi amaçlı makro/piyasa göstergeleri. KARAR KURALI DEĞİLDİR; hata verirse rapor yine üretilir."""
    try:
        vix = fetch_one("^VIX", period="3mo", retries=2)["close"]
        tnx = fetch_one("^TNX", period="3mo", retries=2)["close"]
        irx = fetch_one("^IRX", period="3mo", retries=2)["close"]
        spy = fetch_one("SPY", period="1y", retries=2)["close"]
        return {"vix": float(vix.iloc[-1]), "vix_chg5": float(vix.iloc[-1] - vix.iloc[-6]),
                "curve": float(tnx.iloc[-1] - irx.iloc[-1]), "y10": float(tnx.iloc[-1]),
                "spy_dd": float(spy.iloc[-1] / spy.max() - 1)}
    except Exception as e:
        log.warning("Piyasa bağlamı alınamadı: %s", e)
        return None


def _vix_label(v: float) -> str:
    return "sakin" if v < 15 else "normal" if v < 20 else "gergin" if v < 30 else "stresli" if v < 40 else "panik"


def format_context(c: dict | None) -> list[str]:
    if not c:
        return ["Piyasa durumu: veri alınamadı."]
    dd = c["spy_dd"]
    phase = ("zirveye yakın" if dd > -0.05 else "düzeltme (−%5…−%10)" if dd > -0.10
             else "derin düzeltme (−%10…−%20)" if dd > -0.20 else "ayı piyasası (< −%20)")
    return ["Piyasa durumu (bilgi amaçlı, karar kuralı değil):",
            f"  VIX {c['vix']:.1f} ({_vix_label(c['vix'])}, 5 günde {c['vix_chg5']:+.1f})",
            f"  S&P 500 52h zirveden {dd:+.1%} → {phase}",
            f"  Getiri eğrisi 10Y−3A {c['curve']:+.2f} puan ({'pozitif' if c['curve'] > 0 else 'TERS — tarihsel resesyon öncüsü'}), 10Y %{c['y10']:.2f}"]


def format_report(r: dict, cfg=CONFIG) -> str:
    L = [f"Cloue Portföy · son kapanış {r['date']}",
         f"Değer {r['value']:,.2f} $ · Yatırılan {r['invested']:,.0f} $ · Getiri {r['ret']:+.2%} · Zirveden {r['dd']:.2%}", ""]
    if r["orders"]:
        L.append(f"⚠️ İŞLEM GÜNÜ — {r['reason']}")
        L.append("Önce satışlar. ABD seansı 17:30 TSİ; ~15 dk sonra limit emir (alış +%0,2 / satış −%0,2):")
        for o in r["orders"]:
            lim = o["price"] * (1.002 if o["side"] == "AL" else 0.998)
            L.append(f"  {o['side']:3s} {o['ticker']:7s} {o['qty']:.3f} adet · ≈ {o['usd']:,.2f} $ · limit {lim:.2f}")
        fee = sum(1.5 for o in r["orders"] if not o["ticker"].endswith("-USD"))
        vix = (r.get("context") or {}).get("vix", 0)
        L += [f"Tahmini Midas ücreti: {fee:.1f} $ ({fee / max(r['value'], 1):.2%})",
              "Emir rehberi: 17:45–23:30 TSİ arası gir (seans 17:30–00:00); ilk 15 ve son 10 dakikadan kaçın (spread geniş).",
              "  Limit dolmazsa kovalama — ertesi sabahki raporla yeniden değerlendirilir.",
              "  Kripto satırları Midas Kripto'da TL karşılığıyla; ETF'ler Midas Yatırım'da."]
        if vix >= 30:
            L.append("  VIX ≥ 30: spread'ler açılır, sadece limit emir kullan, emirleri bölme.")
        L.append("Gerçekleşen adet/fiyatları Cloue'ya yaz.")
    else:
        L.append(f"✅ İşlem yok{(' — ' + r['reason']) if r['reason'] else ''}")
    L += [""] + format_context(r.get("context"))
    L += ["", f"Çekirdek %{cfg['core_weight']*100:.0f}: " + ", ".join(f"{t} {w:.0%}" for t, w in cfg["core"].items()),
          "Uydu (rotasyon): " + ", ".join(f"{t} {w:.0%}" for t, w in sorted(r["rotation"].items(), key=lambda x: -x[1]))]
    L += ["Toplam hedef: " + ", ".join(f"{t} {w:.0%}" for t, w in sorted(r["target"].items(), key=lambda x: -x[1]))]
    if r["positions"]:
        L.append("Pozisyonlar: " + ", ".join(
            f"{t} {r['current'].get(t, 0):.0%}" + (f" (SMA altı {r['counters'].get(t, 0)}/{cfg['exit_days']})"
                                                   if r['counters'].get(t, 0) else "")
            for t in r["positions"]))
    if r["value"] > 50_000:
        L += ["", "ℹ️ Portföy 50.000 $'ı aştı: ABD dışı yerleşikler için ABD menşeli varlıklarda 60.000 $ üstü "
                  "ABD veraset vergisi riski var. UCITS (İrlanda) muadillerine geçişi değerlendir."]
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
        r["context"] = market_context()
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
