# Cloue Portföy — Çekirdek + Uydu ETF sistemi

Kural tabanlı; günlük çalışır, **ayda bir** rebalance eder, yalnız trend kırılımında ara işlem üretir.

## Mimari
| Katman | Pay | İçerik | Kural |
|---|---|---|---|
| **Çekirdek** | %50 | NTSX %60 · DBMF %20 · GLD %20 | Hep tutulur, aylık sabit ağırlığa dönülür. Acil çıkış uygulanmaz. |
| **Uydu** | %50 | SPY, QQQ, VEA, VWO, AVUV, NTSX, DBMF, GLD, BTC, ETH | Skor = 1/3/6/12 ay getiri ort. · SMA200 üstü · en iyi 3 · ters volatilite · boş slot → BIL · kripto ≤ %20 · 3 kapanış SMA200 altı → sat, BIL |

Neden çekirdek? Return stacking (NTSX) ve CTA (DBMF) **sürekli tutulduğunda** çeşitlendirme sağlar; momentum rotasyonuna sokulunca etkileri kaybolur (aşağıdaki test).

## Backtest (2020-09 → 2026-11, %0,10 maliyet) — `python3 backtest.py --start 2019-09-26 --crypto --core 0.5`
| | CAGR | Vol | Sharpe | MaxDD |
|---|---|---|---|---|
| Prompt aynen (8 ETF rotasyon, kriptosuz) | 13,0% | 13,1% | 1,00 | −14,8% |
| Eski 5 ETF rotasyon, kriptosuz | 13,4% | 12,7% | 1,05 | −15,2% |
| Uydu (8 ETF + BTC/ETH) | 20,9% | 16,7% | 1,22 | −25,4% |
| Çekirdek (NTSX/DBMF/GLD) | 12,2% | 11,7% | 1,05 | −16,2% |
| **Cloue = %50 çekirdek + %50 uydu** | **16,8%** | **12,5%** | **1,30** | **−18,6%** |
| SPY al-tut | 16,2% | 16,6% | 0,99 | −24,5% |

Sınırlar: 6 yıllık örneklem (AVUV/DBMF 2019'da başladı), 2008 gibi uzun bir ayı piyasası içermiyor; BTC/ETH geriye dönük seçildi. Farklar tek dönemden; gerçek beklenti daha düşük olmalı.

## Dosyalar
- `portfolio_engine.py` — veri (yfinance → yedek doğrudan Yahoo API, tekrar denemeli), sinyal, karar, rapor, durum (`portfoy.json`, atomik yazım).
- `telegram_notifier.py` — Telegram Bot API, parçalama + 429/ağ hatası toleransı.
- `../.github/workflows/daily_run.yml` — hafta içi 08:47 TSİ, durumu repoya geri yazar.
- `islem.py` — gerçekleşen işlem / katkı kaydı. `backtest.py`, `tests/test_engine.py`.

## Günlük akış
1. Rapor gelir (Telegram). Çoğu gün "işlem yok".
2. İşlem günü: emirleri Midas'ta ABD seansında gir, gerçekleşenleri yaz:
   `python3 islem.py AL NTSX 5.035 59.60 --dengeleme` (rebalance/başlangıç işlemlerinde `--dengeleme`)
3. Aylık katkı: `python3 islem.py YATIR 1000 <o anki portföy değeri>` → ertesi gün KATKI emirleri (satışsız).

Bu bir araştırma/eğitim sistemidir; yatırım danışmanlığı değildir.
