"""
gunluk_deneme.py — 500 $'lık GÜNLÜK SANAL (paper) hesap. Gerçek para kullanmaz.

Amaç: "günlük al-sat" fikrini gerçek parayı riske atmadan, Midas ücretleri (1,5 $/emir) dahil,
canlı veriyle 3 ay ölçmek. Gerçek 500 $ bu sürede BIL'de (her gün faiz) bekler; karşılaştırma raporda.

Strateji (önceden sabit, değiştirilmez): Connors RSI(2) — SPY
  GİRİŞ : kapanışta RSI(2) < 10 VE fiyat > SMA200  -> tümüyle SPY al
  ÇIKIŞ : kapanış > SMA5                           -> tümünü sat
  Boşta : nakit BIL getirisi kazanır
Backtest (2008→2026): ücretsiz yıllık +%5,5; 1,5 $/emir ile +%0,2, maxDD −%30 (arastirma notu, README).

Her sabah portfolio_engine tarafından çağrılır; aynı kapanış günü iki kez işlenmez.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

import portfolio_engine as pe

STATE = pe.ROOT / "deneme500.json"
FEE = 1.5
START_CAPITAL = 500.0


def _rsi2(s: pd.Series) -> pd.Series:
    r = s.diff()
    up = r.clip(lower=0).ewm(alpha=1 / 2).mean()
    dn = (-r.clip(upper=0)).ewm(alpha=1 / 2).mean()
    return 100 - 100 / (1 + up / dn)


def load() -> dict:
    try:
        return json.loads(STATE.read_text())
    except FileNotFoundError:
        return {"nakit": START_CAPITAL, "adet": 0.0, "pozisyonda": False, "son_gun": None,
                "bil_referans": None, "islemler": [], "baslangic": None, "ucret_toplam": 0.0}


def step(adj: pd.DataFrame, close: pd.DataFrame) -> dict:
    """Son kapanışı işler ve özet döndürür. adj/close portfolio_engine.fetch_prices çıktısı."""
    st = load()
    day = str(adj.index[-1].date())
    spy, bil = adj["SPY"], adj["BIL"]
    px = float(close["SPY"].iloc[-1])
    rsi = float(_rsi2(spy).iloc[-1])
    sma200 = float(spy.iloc[-200:].mean())
    sma5 = float(spy.iloc[-5:].mean())
    action = "bekle"
    if st["baslangic"] is None:
        st["baslangic"], st["bil_referans"] = day, float(bil.iloc[-1])
    if st["son_gun"] != day:
        # boşta geçen günlerin BIL faizi
        if st["son_gun"] and not st["pozisyonda"]:
            prev = bil[bil.index <= pd.Timestamp(st["son_gun"])]
            if len(prev):
                st["nakit"] *= float(bil.iloc[-1] / prev.iloc[-1])
        if not st["pozisyonda"] and rsi < 10 and float(spy.iloc[-1]) > sma200:
            st["adet"] = (st["nakit"] - FEE) / px
            st["nakit"], st["pozisyonda"] = 0.0, True
            st["ucret_toplam"] += FEE
            action = f"AL SPY {st['adet']:.3f} @ {px:.2f}"
        elif st["pozisyonda"] and float(spy.iloc[-1]) > sma5:
            st["nakit"] = st["adet"] * px - FEE
            st["adet"], st["pozisyonda"] = 0.0, False
            st["ucret_toplam"] += FEE
            action = f"SAT SPY @ {px:.2f}"
        if action != "bekle":
            st["islemler"].append({"gun": day, "islem": action})
        st["son_gun"] = day
        STATE.write_text(json.dumps(st, indent=2, ensure_ascii=False))
    value = st["nakit"] + st["adet"] * px
    bil_value = START_CAPITAL * float(bil.iloc[-1]) / st["bil_referans"]
    return {"gun": day, "deger": value, "bil_deger": bil_value, "aksiyon": action, "rsi": rsi,
            "pozisyonda": st["pozisyonda"], "islem_sayisi": len(st["islemler"]),
            "ucret": st["ucret_toplam"], "baslangic": st["baslangic"]}


def format_section(s: dict) -> list[str]:
    return ["", f"🧪 Günlük deneme hesabı (SANAL 500 $, {s['baslangic']}'den beri, RSI(2) SPY):",
            f"  Bugün: {s['aksiyon']} · RSI2 {s['rsi']:.0f} · {'SPY tutuluyor' if s['pozisyonda'] else 'nakitte'}",
            f"  Deneme {s['deger']:.2f} $ ({s['deger']/START_CAPITAL-1:+.2%}) vs aynı 500 $ BIL'de {s['bil_deger']:.2f} $ "
            f"({s['bil_deger']/START_CAPITAL-1:+.2%}) · {s['islem_sayisi']} işlem, ücret {s['ucret']:.1f} $"]
