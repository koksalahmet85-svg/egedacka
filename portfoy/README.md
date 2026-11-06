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

## Araştırma bulguları (2026-11-06) — `arastirma/`
**Uzun test (2007-06 → 2026-11, GFC dahil, kriptosuz).** Kısa geçmişli ETF'ler vekillerle uzatıldı:
AVUV←VBR (korelasyon 0,97), NTSX←0,9·SPY+0,6·(IEF−BIL) (0,96), DBMF←sentetik TSMOM (DBMF ile aylık korelasyon 0,67; DBMF–AQMIX 0,73).

| | CAGR | Vol | Sharpe | MaxDD |
|---|---|---|---|---|
| **Cloue (canlı ayar, kriptosuz)** | 9,0% | 11,5% | 0,81 | −19,2% |
| Sadece uydu (rotasyon) | 7,7% | 13,3% | 0,62 | −20,4% |
| Sadece çekirdek (NTSX/DBMF/GLD) | 10,1% | 11,9% | 0,87 | −25,4% |
| SPY al-tut | 10,4% | 19,7% | 0,60 | −55,2% |

- **Parametre platosu:** top_n 2–4, SMA 150–250, lookback (1/3/6/12, 3/6/12, 12), skor>0 şartı: Sharpe 0,78–0,82, CAGR 8,7–9,1%. Sonuç parametreye duyarlı değil → ayar yapılmadı (aşırı uyum riski).
- **Getirinin motoru çekirdek**, rotasyon değil: rotasyonun katkısı düşüşü sınırlamak (alt dönem 2008-12: Cloue −17,8% vs SPY −51,9%). Çekirdek %50–70 aralığı plato (Sharpe 0,81–0,85); %50 korundu.
- **Acil çıkış kuralı** kapatılınca CAGR +0,5 puan, MaxDD −1,4 puan kötü; Sharpe aynı. Nötr — kullanıcı kuralı olarak korundu.
- **Gerçekçi beklenti:** uzun vadede yıllık ~%8–10 (2020-26'daki %16,8 kripto ve güçlü dönem etkisi).

**Midas ücreti (1,5 $/emir), 1000 $ + 1000 $/ay simülasyonu** (`arastirma/maliyet.py`): ücret yatırılanın ~%0,5–0,7'si, IRR'a etkisi 0,1–0,25 puan. Çeyreklik rotasyon IRR'ı 0,5–2,4 puan düşürdü → aylık rotasyon kalıyor.
"Akıllı katkı" (nakit en eksik 2 varlığa; tam rebalance yalnız seçim değişirse veya sapma >%10; min emir 50 $) emir sayısını ~%20 azalttı, IRR kaybı yok → **canlıya alındı**. Daha az emir = daha az iş + daha az vergilendirilebilir satış.

**Veri kalitesi koruması:** son kapanış 4 günden eskiyse, ETF'de tek günde >%25 hareket varsa veya kripto verisi bayatsa rapor üretilmez, Telegram'a hata gider.

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
