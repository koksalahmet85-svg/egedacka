# Sözleşmenin Anatomisi: Teraslar (proje paketi)

Spor Finansı ve Muhasebesi dersi, 5. hafta için 3:34'lük açıklayıcı film. cinecode ile, kodla yapılıyor.

## Nerede kaldık
- Onaylanan adımlar: görüşme, yol haritası, senaryo (v2, kilitli), stil karesi (`review/style-v1.png`), yazı tipi (IBM Plex).
- Sıradaki adım: anlatıcı ses denemeleri, ardından animatik (5. adım).
- Ayrıntılar `STATE.md` dosyasının "Resume here" bölümünde.

## Önemli dosyalar
- `SCRIPT.md`: kilitli senaryo (279 kelime) ve ekran yazıları
- `ROADMAP.md`: dört perde, planlar, yönetmen kartı
- `shots.json`: 28 plan, zamanlarıyla
- `research/facts.md`: her rakamın kaynağı ve doğrulanma durumu
- `engine/teraslar.html`: sahne kodu (three.js), `engine/looks.mjs` içindeki `kesit-cizimi` görünüşü
- `review/`: yön panosu, stil karesi, yazı tipi panosu

## Kendi bilgisayarında devam etmek
1. Node 22+, Python 3, ffmpeg ve Chrome kurulu olsun.
2. cinecode'u kur: `git clone https://github.com/sarpstar/cinecode.git ~/.claude/skills/cinecode`
3. Bu zip'i `~/Filmler/` klasörüne aç; böylece `~/Filmler/sozlesmenin-anatomisi` oluşur.
4. Claude Code'u `~/Filmler` klasöründe aç ve "STATE.md'den devam et" yaz.
5. Ses için ücretsiz bir Gemini anahtarı al (aistudio.google.com/apikey). Claude anahtarı `tools/keys.py` ile gizli bir dosyaya kaydeder; anahtarı sohbete yapıştırma.

GPU'lu bir bilgisayarda render dakikalar sürer. Bulut ortamında (GPU yok) bir kare 5,4 saniyede çizildi; tam film yaklaşık 8 saat sürerdi.

## Doğrulanmayan ve filmden çıkarılanlar
- Fenerbahçe'nin 2025'te %70'i aşması: yalnızca tek ve zayıf bir kaynakta geçiyor.
- Aston Villa cezasının 15 m€'luk koşullu kısmı: bulunamadı.
- EuroLeague'in 0,50 / 0,75 / 1,00 vergi dilimleri: Panathinaikos'un ödediği oran bu dilimlerle uyuşmuyor.
