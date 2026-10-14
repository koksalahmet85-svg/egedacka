# Ege Alfa Spor Kulübü — Kulüp Yönetim Sistemi

750 sporcu, 35 personel ölçeği için uçtan uca kulüp yönetimi: **Koç & İK · Sporcu & Veli Portalı · Finans · CRM / Reklam ROI**.

| Katman | Teknoloji |
|---|---|
| Şema & migration | Prisma 6 (`prisma/schema.prisma`, tek doğruluk kaynağı) |
| API | FastAPI + asyncpg (PostgreSQL 16) |
| Arka plan işleri | APScheduler worker (fatura, gecikme alarmı, hafta üretimi, puantaj, rapor, bildirim outbox) |
| Panel | Next.js 16 (App Router) · TypeScript · Tailwind 4 |
| Altyapı | Docker Compose: `db`, `migrate`, `api`, `worker`, `web` |

> Mevcut `index.html` (Ege Daçka performans sistemi) olduğu gibi duruyor. Ölçüm kataloğu (dribbling, pas, şut, sprint10/20, CMJ, T-test, V-cut, boy, kulaç, oturma boyu) aynı kodlarla yeni sisteme taşındı, böylece veriler aktarılabilir.

## Hızlı başlangıç

```bash
cp .env.example .env            # JWT_SECRET'ı doldurun
docker compose up -d --build
docker compose run --rm api python -m app.seed   # opsiyonel: 750 sporculuk SENTETİK demo
```

Panel: http://localhost:3000 · API dokümanı (Swagger): http://localhost:8000/api/docs
Demo girişleri (şifre `demo1234`): `admin@`, `direktor@`, `koc@`, `muhasebe@`, `pazarlama@egealfa.com`

Docker olmadan geliştirme:

```bash
npm install && DATABASE_URL=postgresql://... npx prisma migrate deploy
cd backend && pip install -r requirements-dev.txt && uvicorn app.main:app --reload
python -m pytest            # 33 test; yerel PostgreSQL'de geçici "egealfa_test" DB açar
cd ../frontend && npm install && npm run dev
```

## Mimari kararlar (neden böyle?)

### 1. Odoo / ERPNext / Cal.com yerine özel mimari
| Seçenek | Karar | Gerekçe |
|---|---|---|
| **Odoo** | ✗ çekirdek olarak değil | Enterprise modülleri (muhasebe TR lokalizasyonu, pazarlama) ücretli; spor-bilimi metrikleri, deneme antrenmanı hunisi, takım/saha çakışma kuralı için ciddi özelleştirme gerekir. Özelleştirilmiş Odoo'yu güncellemek pahalıdır. |
| **ERPNext** | ✗ | Education modülü okul mantığında (dönem, not); sRPE yükü, olgunlaşma (PHV), kutu skor yok. Frappe öğrenme eğrisi 2-3 kişilik bir ekip için ağır. |
| **Cal.com** | ✗ | Randevu (1:1 booking) için tasarlanmış; tekrarlayan takım antrenmanı + saha kapasitesi + koç çakışması modelini karşılamıyor. AGPL lisansı da ek yük. Bunun yerine çakışma kuralı **PostgreSQL exclusion constraint** ile veritabanında zorlanıyor (aşağıda). |
| **Muhasebe** | Entegrasyon | Resmî defter mali müşavirin yazılımında kalır (Logo/Mikro/Paraşüt). Sistem **ön muhasebe + tahsilat + nakit akışı** tutar; e-Arşiv faturası GİB'e **özel entegratör API'si** üzerinden gönderilir (`earchive_status`, `earchive_uuid` alanları hazır). |

### 2. Prisma şema sahibi, asyncpg sorgu sahibi
Prisma Client Python **artık bakım görmüyor** (repo arşivlendi). Bu yüzden: şema ve migration'lar Prisma CLI ile (`migrate` container'ı), FastAPI tarafı asyncpg ile aynı tablolara ham SQL yazar. Tüm tablo/kolonlar `@@map`/`@map` ile snake_case → SQL okunur. `prisma migrate diff` ile drift **sıfır** doğrulandı.

### 3. İş kuralları veritabanında
`prisma/migrations/*_constraints/migration.sql`:
- **Saha ve koç çakışması imkânsız**: `EXCLUDE USING gist (facility_id WITH =, tstzrange(...) WITH &&)` — hangi istemci yazarsa yazsın. API bunu 409 + Türkçe mesaja çevirir.
- Sporcunun tek aktif takımı (partial unique index), tutar/oran CHECK'leri.
- **Fatura ödenen tutarı ve statüsü trigger ile tahsilattan türetilir** — tek yazım noktası.
- "Gecikmiş" bir statü olarak saklanmaz; `v_invoice_balance` görünümünde hesaplanır (gece job'ı kaçsa da veri yanlış olmaz).

### 4. Her otomasyon idempotent
| İş | Garanti |
|---|---|
| Aylık fatura | `UNIQUE(subscription_id, period)` → iki kez çalışsa ikinci fatura kesilmez |
| Hafta üretimi | `UNIQUE(plan_id, starts_at)`; çakışan seans tüm haftayı düşürmez, rapor edilir |
| Puantaj | `time_entries.session_id UNIQUE` → yoklamayı iki kez kaydetmek ikinci satır üretmez |
| Gecikme hatırlatması | `UNIQUE(invoice_id, level)` → veli aynı mesajı iki kez almaz; kaçırılan gün ertesi gün yakalanır |
| Meta lead webhook | `external_lead_id UNIQUE` + 30 gün telefon tekilleştirme (çift sayım CPL'yi yapay düşürür) |
| Ödeme webhook | `provider_ref UNIQUE`, HMAC imza doğrulama |
| SMS/WhatsApp | Transactional outbox + `FOR UPDATE SKIP LOCKED` (çoklu worker güvenli) |

### 5. Dashboard veri akışı (tek ekran, tek istek)
```
Tarayıcı ──(ilk yük)──> Next.js sunucu bileşeni ──(iç ağ, Bearer)──> GET /api/v1/dashboard/executive
   │                                                                   └─ 7 alt sorgu asyncio.gather ile PARALEL
   └──(filtre/yenile)──> /api/backend/* route handler (httpOnly cookie → Bearer) ──┘   + 60 sn TTL cache
```
- `frontend/lib/useExecutiveDashboard.ts`: AbortController ile yarış durumu engeli, stale-while-revalidate, aralık başına bellek önbelleği, yalnız sekme görünürken 60 sn yenileme, üstel geri çekilmeli 3 deneme, 401 → login.
- JWT **httpOnly cookie**'de; tarayıcı JS'i token'ı hiç görmez (XSS'e karşı).
- Seed'li veride (750 sporcu, 4.500 fatura, 3.245 lead) yanıt süresi **~130 ms**; tüm diğer uçlar < 40 ms.

### 6. ROI'yi doğru ölçmek
- **Kohort hunisi**: seçilen aralıkta *oluşan* lead'ler bugüne kadar izlenir (aralıkta kazanılanı aralıkta gelen lead'e bölmek oranı şişirir).
- **Gerçekleşen ROAS** yalnız **kayıt tarihinden sonraki** tahsilatı kampanyaya atfeder.
- **Öngörülen ROI** = (kayıt × LTV − harcama) / harcama. LTV = ortalama aylık aidat × ortalama üyelik süresi; ayrılan sporcu sayısı 20'yi geçene kadar `DEFAULT_LIFETIME_MONTHS=18` varsayımı kullanılır (erken ayrılanlar ortalamayı aşağı yanlılar).
- Kampanyaya bağlı offline giderler (okul tanıtımı, baskı) `expenses.campaign_id` ile harcamaya eklenir.
- `click_id` (fbclid/gclid) saklanır → kayıtları Meta/Google'a offline conversion olarak geri bildirip algoritmayı "kayıt olan veli"ye optimize etmek mümkün.

## Spor bilimi katmanı (kanıta dayalı)
| Özellik | Yöntem | Kaynak |
|---|---|---|
| Antrenman yükü | sRPE = RPE (CR-10) × dakika | Foster et al. 2001, *JSCR* 15(1) |
| Haftalık monotoni / strain | ort. günlük yük / SD | Foster 1998, *MSSE* 30(7) |
| Gerçek gelişim mi? | SWC = 0.2 × grup SD + ölçüm hatası (TE) kontrolü | Hopkins 2004, *Sportscience* 8 |
| Biyolojik olgunluk | PHV'ye kalan yıl (maturity offset) | Moore et al. 2015, *MSSE* 47(8) |
| Yaş grubu kıyası | aynı doğum yılı içinde yön düzeltilmiş z-skoru | — |
| Şut verimliliği | eFG%, TS%, AST/TOV | Oliver 2004 |
| Göreceli yaş etkisi | doğum çeyreği | RAE literatürü |

**Bilinçli olarak kullanılmayan:** ACWR (akut:kronik yük oranı) — sakatlık tahmin aracı olarak metodolojik açıdan çürütüldü (Impellizzeri et al. 2020, *IJSPP* 15(6)).
**Uyarı:** `metric_definitions.typical_error` değerleri literatür yaklaşığıdır; kulübün kendi test-tekrar test ölçümüyle güncellenmelidir.

## Modül → endpoint haritası (79 uç)
| Modül | Önek | Öne çıkanlar |
|---|---|---|
| Kimlik | `/auth` | login (OAuth2 form), me |
| Sporcu & veli | `/athletes` | KVKK rızasız kayıt yok · transfer (geçmiş korunur) · `progress` (SWC, z, PHV, maç) · `attendance-trend` · `metrics/{code}` · `balance` |
| Takım & tesis | `/teams`, `/facilities` | kadro doluluğu · `facilities/utilization` (kira optimizasyonu) |
| Antrenman | `/training` | şablon → `weeks/{monday}/generate` · seans taşı/iptal · drill blokları · toplu yoklama = otomatik puantaj · `teams/{id}/load` |
| Koç & İK | `/hr` | personel · vardiya · manuel puantaj · `timesheets/{ay}/close` · `payroll/{ay}/draft` · ödendi → puantaj kilitlenir |
| Performans | `/performance` | test bataryası · takım sıralaması · kutu skor (tutarlılık kontrolü) · aylık rapor üret/yayımla |
| Finans | `/finance` | aidat planı · abonelik/dondurma · `invoices/run/{ay}` · tahsilat + makbuz · gecikme listesi · nakit akışı · **takım bazında katkı payı** |
| CRM | `/crm` | lead (tekilleştirme) · temas · aşama · deneme antrenmanı · `convert` (lead→sporcu tek transaction) · harcama upsert · funnel · roi |
| Tahsilat defteri | `/ledger`, `/seasons` | Excel import · anomaliler · sezon karşılaştırma (economic/cash) · dönmeyen oyuncular |
| Yönetim | `/dashboard/executive` | finans + pazarlama tek yanıt |
| Veli portalı | `/portal` | çocuklar · 14 günlük takvim · raporlar · devam grafiği · fatura/makbuz (guardian_id JWT'den) |
| Webhook | `/webhooks` | Meta Lead Ads (doğrulama + HMAC) · ödeme sağlayıcı |

Yetki: `ADMIN`, `MANAGER`, `COACH` (yalnız kendi takımları/seansları), `ACCOUNTANT`, `MARKETING`, `GUARDIAN` (yalnız kendi çocukları). Testler bu izolasyonu doğrular.

## Tahsilat defteri (Excel) ve sezon karşılaştırma

Sistem öncesi aylık Excel defterleri (`TEMMUZ 25`, `AĞUSTOS 26` … sayfaları) panelden **Sezon karşılaştırma → Defteri yükle** ile ya da `POST /api/v1/ledger/import` ile içe aktarılır.

- **Sezon aralıkları** yönetici tarafından tanımlanır: `PUT /api/v1/seasons` (ör. `2025-2026: 2025-07-01 → 2026-07-31`, `2026-2027: 2026-08-01 → 2027-07-31`).
- **Serbest metin "DÖNEM"** sınıflandırılır: aylık, kısmi (yarım/eksik), çok aylık, sezonluk peşin, sezonluk taksit, tekstil, etkinlik (İstanbul, Yeşil Tribün), geçmiş borç, iptal.
- **Veri kalitesi sessizce düzeltilmez**: hatalı tarih (`01.08.205`), metin tutar (`₺4.700,00`, `₺5,200.00`), TUTAR ≠ AİDAT+FORMA uyuşmazlığı vb. her düzeltme `GET /ledger/anomalies` listesine düşer. Tekstilsiz satırda iki tutar çelişirse **küçük olan** alınır (gelir şişmez).
- **Yeniden yükleme güvenli**: dosyadaki sayfalar tamamen değiştirilir (defter canlı belge; satır kayması bozmaz).
- **İki hesap modu**: `cash` (her ödeme defter sayfasının sezonuna) ve `economic` (önerilen: Temmuz'da alınan sezonluk peşin/taksit yeni sezona yazılır).
- **Hizalanmış kıyas**: hedef sezonun kapsadığı aylar, son ayda aynı güne kadar, geçen yılın aynı penceresiyle kıyaslanır.
- **Sezonluk peşin ↔ 12 ay aylık**: sezonluk plan 12 ay kapsar (sezon bitişinden geriye 12 ay). Peşin fiyatı, defterdeki fiili aylık fiyat merdiveniyle aynı 12 ayın toplamına kıyaslanır; gelmemiş aylar son fiyatla doldurulur ve "başabaş zam" (peşinin aylıkla eşitlenmesi için kalan aylarda gereken zam) raporlanır.
- `GET /ledger/not-returned`: geçen sezonun son 3 ayında ödeyip bu sezon henüz ödemeyenler (geri kazanım arama listesi).
- Defter tahsilatları `v_cash_movements` görünümüne `LEDGER_*` kategorileriyle girer. **Canlı tahsilata geçilen aydan sonra defter yüklenmemelidir** (çift sayım).
- Gerçek defter dosyaları `.gitignore` ile repodan dışlanmıştır; testler sentetik çalışma kitabı üretir.

## Bilinen sınırlar / sonraki adımlar
- e-Arşiv entegratörü, SMS (Netgsm/İleti Merkezi) ve WhatsApp Cloud API sağlayıcıları arayüz olarak hazır (`services/notify.py → Sender`), gerçek bağlantı anahtarları gelince takılmalı.
- Bordroda net/SGK/vergi kalemleri mali müşavirden girilir; sistem brüt + yaklaşık işveren maliyetini (×1.2075) gider olarak tanır.
- PDF rapor üretimi (veli raporu) ve koç mobil yoklama ekranı henüz yok; API'leri hazır.
- Docker imajları bu ortamda build edilmedi (Docker daemon yok); compose dosyası `docker compose config` ile doğrulandı.
