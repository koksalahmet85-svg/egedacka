# Cloue Portföy — 1000 $ ile birlikte yönetim

**Model:** Kural tabanlı ETF rotasyonu (momentum + trend filtresi). Günlük *mesaj*, aylık *işlem*.
Kararı tahmin değil kurallar verir. Kurallar: `strateji.py` başındaki açıklama.

## Geçmiş test (2008-08 → 2026-11, %0,10 işlem maliyeti dahil)
| | Yıllık getiri | Volatilite | Sharpe | Maks. düşüş |
|---|---|---|---|---|
| **Cloue** | 9,2% | 12,4% | 0,77 | **−17,2%** |
| SPY al-tut | 12,3% | 19,7% | 0,69 | −47,2% |
| 60/40 | 9,0% | 11,4% | 0,82 | −27,7% |

### Kripto eklendikten sonra (BTC+ETH, en fazla %20) — 2018-11 → 2026-11
| | Yıllık getiri | Volatilite | Sharpe | Maks. düşüş |
|---|---|---|---|---|
| **Cloue + kripto** | 16,3% | 17,0% | 0,98 | −25,9% |
| Cloue kriptosuz | 11,2% | 12,6% | 0,91 | −15,7% |
| SPY al-tut | 15,9% | 19,3% | 0,86 | −33,7% |

Uyarı: BTC ve ETH bugünün kazananları olduğu için seçildi (geriye dönük seçim yanlılığı); bu dönem kriptonun en iyi on yılıdır. Gelecekte bu farkın küçülmesini bekle.

Dürüst okuma (ETF-only, 2008→): getiri boğa piyasasında S&P 500'ün gerisinde kalır; avantajı krizlerde **yarı-üçte bir düşüş**.
4 varyant denendi (vol hedefi açık/kapalı × günlük kural açık/kapalı), Sharpe 0,73–0,82 — farklar istatistiksel olarak anlamsız; en az kurallı + en düşük düşüşlü olan seçildi.

## Akış
1. Her iş günü sabah Cloue `python3 gunluk.py` çalıştırır, raporu `raporlar/` altına yazar ve bildirim atar.
2. Çoğu gün: **"işlem yok"**. Ayda ~1 gün (ve nadiren trend çıkışında): emir listesi.
3. Sen emirleri ABD seansında (17:30 TSİ sonrası) girersin, gerçekleşen adet/fiyatı yazarsın.
4. Cloue `python3 islem.py AL SPY 0.488 765.10 --dengeleme` ile kaydeder.

## Değişmez kurallar
- Kurallar dışında işlem yok. Fikir gelirse önce backtest, sonra karar.
- Değerlendirme dönemi: en az 12 ay. Tek ay/çeyrek sonucu sinyal değil, gürültüdür.
- Bu bir araştırma/eğitim sistemidir; lisanslı yatırım danışmanlığı değildir.
