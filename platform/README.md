# Ege Alfa Spor Kulübü: Kulüp Yönetim Sistemi

750 sporcu ve 35 personel için uçtan uca yönetim sistemi. Python (FastAPI), PostgreSQL (Prisma), Next.js (TypeScript, Tailwind) ve Docker ile yazıldı.

## 1. Karar: Odoo veya ERPNext çekirdek olmasın

Önerim şu: **çekirdek bu repodaki özel sistem olsun, hazır açık kaynak araçları yalnızca iyi oldukları dar işlerde entegre edin.**

| Seçenek | Değerlendirme | Bu sistemdeki yeri |
|---|---|---|
| **Odoo** | Esnek, ama tam muhasebe ve Türkiye e-Fatura ihtiyacı pratikte Enterprise lisansı ve yerelleştirme partneri gerektiriyor. Spor alanına özgü modeller (sRPE yükü, box score, saha çakışma kısıtı, olgunlaşma bantları) yerleşik değil, Odoo ORM'u üzerinde özel modül yazmak gerekir. Asıl maliyet lisans değil, özelleştirme bakımı. | Kullanılmıyor |
| **ERPNext** | Ücretsiz ve güçlü. Ancak v14'ten beri Education ve HRMS ayrı uygulamalar. MariaDB ve Frappe yığını, seçilen PostgreSQL/FastAPI/Next.js yığınıyla çakışıyor ve iki ayrı platform işletmek gerekir. | Kullanılmıyor |
| **Cal.com** | Herkese açık randevu için çok iyi, kulübün iç programı için uygun değil. Tekrarlayan takım antrenmanı, saha kapasitesi ve koç çakışması burada veritabanı kısıtıyla çözülüyor. | **Yalnızca deneme antrenmanı rezervasyonu** (webhook, `docker compose --profile calcom`) |
| **Paraşüt** | Türkiye e-Arşiv/e-Fatura ve ön muhasebe; mali müşavirler yaygın kullanıyor. | Fatura adaptörü (`services/invoicing.py`) |
| **iyzico** | Kayıtlı kartla otomatik aidat çekimi | `Subscription.autoPayToken` alanı hazır, adaptör yol haritasında |
| **Meta Lead Ads, Marketing API, WhatsApp Cloud API** | Lead alımı, reklam harcaması, borç hatırlatma | Webhook, gece senkronu ve bildirim outbox'ı yazıldı |

> ⚠️ **Teknik risk, ilk bilmeniz gereken:** İstenen yığın "Python + Prisma". Python tarafındaki istemci (`prisma-client-py`) artık aktif geliştirilmiyor. Bu yüzden sürümü sabitledim (0.15.0) ve mimariyi riske göre kurdum. **Şema ve migration'lar Prisma'da kalıyor**, ama tüm iş kuralları `app/domain/` altında, veritabanından bağımsız saf fonksiyonlar. İleride SQLAlchemy veya asyncpg'ye geçmek gerekirse yalnızca router/servis katmanındaki sorgular değişir; testler ve kurallar aynen kalır.

## 2. Mimari

```
                 ┌─────────────── Next.js (web) ───────────────┐
 Tarayıcı ──────▶│ RSC: ilk veri sunucuda çekilir               │
  (httpOnly      │ /api/backend/* BFF proxy (token JS'e inmez)  │
   çerez)        └──────────────────────┬──────────────────────┘
                                        │ Bearer JWT
 Meta / Cal.com ──▶ /webhooks/*  ┌──────▼──────┐     ┌──────────────┐
  (HMAC imzalı)                  │ FastAPI api │────▶│ PostgreSQL 16│
                                 └──────┬──────┘     │ EXCLUDE,     │
                                        │            │ CHECK, view  │
                                 ┌──────▼──────┐     └──────▲───────┘
                                 │ worker      │────────────┘
                                 │ (APScheduler│──▶ WhatsApp / Paraşüt / Meta Insights
                                 │  tek süreç) │
                                 └─────────────┘
```

### Modüller arası veri zincirleri

1. **Antrenman → puantaj → bordro → gider → kâr/zarar.** Koç seansı "tamamla"r ve süre otomatik olarak koçun puantajına yazılır. Yönetici onaylar, bordro onaylı puantajdan hesaplanır. Bordro "ödendi" olunca `Expense(SALARY)` oluşur ve aylık gelir-gider kendiliğinden güncellenir.
2. **Kampanya → lead → deneme → sporcu → aidat → ROI.** Meta webhook'u lead'i kampanyasıyla birlikte kaydeder. Cal.com rezervasyonu `TrialBooking` oluşturur. `convert` adımı sporcu, veli, takım üyeliği ve aboneliği tek transaction'da kurar (kardeş indirimi otomatik). O sporcudan tahsil edilen her ödeme `v_lead_revenue` görünümü üzerinden kampanyaya atfedilir. Kampanya bazlı ROI bu şekilde **gerçek tahsilattan** hesaplanır, tahminden değil.
3. **Abonelik → aylık tahakkuk → tahsilat → fatura → gecikme alarmı.** Her ayın 1'inde tahakkuk üretilir (idempotent). Ödeme en eski borçtan başlayarak (FIFO) dağıtılır ve satır kilidiyle korunur. Fatura arka planda kesilir; entegratör hata verirse yeniden denenir. Gecikmede D+3 / D+10 / D+20 kademeli hatırlatma gider, son kademede yöneticiye eskalasyon yapılır.

## 3. İstenen çıktılar: nerede?

| # | Çıktı | Dosya |
|---|---|---|
| 1 | Prisma şeması (40+ model, ilişkiler) | `backend/prisma/schema.prisma` |
| 1b | Prisma'nın ifade edemediği kısıtlar ve görünümler | `backend/prisma/migrations/*_constraints_views/migration.sql` |
| 2 | FastAPI router'ları (84 API + 3 webhook endpoint) | `backend/app/routers/*.py` |
| 3 | Finans + ROI dashboard veri çekme mantığı | `frontend/app/(admin)/dashboard/page.tsx`, `frontend/components/dashboard/FinanceRoiDashboard.tsx`, `frontend/lib/api/*` |

### Endpoint haritası (`/api/v1`)

| Modül | Önek | Öne çıkanlar |
|---|---|---|
| Kimlik | `/auth` | `login`, `me` (JWT, 7 rol, satır bazlı yetki) |
| Sporcu | `/athletes` | kayıt (veli eşleşmesi + kardeş indirimi), `attendance-trend`, `maturity` |
| Veli portalı | `/portal` | `children`, `reports` (yalnızca yayınlanmış), `schedule`, `billing` |
| Koç & İK | `/hr` | personel, `staff/{id}/schedule`, vardiya (çakışma kontrolü), `timesheet/clock/in\|out`, puantaj onayı, izin, `payroll/build→approve→paid`, `coach-load`, `expiring-licenses` |
| Antrenman | `/training` | tesis/saha, takım, `slots`, `plans/generate` (çakışma → 409 + liste, `dryRun`), drill'ler, toplu yoklama + RPE, `complete`, `courts/utilization` |
| Performans | `/performance` | toplu test girişi, `progress` (takım ortalamasıyla), box score (tutarlılık doğrulaması + PIR/eFG/TS), aylık rapor `generate→publish` |
| Finans | `/finance` | aidat planı, abonelik, `charges/generate-monthly`, ödeme (FIFO), iade, borç silme (yönetici + gerekçe), faturalar, gider, `pnl`, `aging` |
| CRM | `/crm` | kampanya, harcama aktarımı, lead (tekrar kontrolü), aşama (geri gidiş yasak), aktivite (ilk temas → CONTACTED), deneme, `convert`, `sla-breaches`, `lost-reasons` |
| Panel | `/dashboard/overview` | finans ve pazarlama ROI tek yanıtta |
| Webhook | `/webhooks/meta`, `/webhooks/calcom` | HMAC-SHA256 doğrulama, ham olay kaydı, idempotent |

## 4. Dashboard veri çekme mantığı

```
RSC page.tsx ──serverFetch──▶ FastAPI /dashboard/overview ──asyncio.gather──▶ 4 SQL (paralel)
     │                                                         └─ 60 sn bellek önbelleği,
     ▼                                                            yazma işlemlerinde temizlenir
SWRConfig fallback = { [anahtar]: veri }   ← aynı anahtar → hydration'da ikinci istek yok
     │
useSWR(anahtar)  keepPreviousData · refreshInterval 60 sn · odakta yenile
     │           401/403'te tekrar deneme yok, diğer hatalarda üstel geri çekilme (3 deneme)
     ▼
Aralık butonu: üzerine gelince preload() (önceden ısıtma), tıklayınca history.replaceState (sunucu yeniden render edilmez)
```

- **Tek istek (BFF):** Frontend dört ayrı endpoint yerine tek bir toplu yanıt alır.
- **Güvenlik:** Token httpOnly çerezde tutulur, tarayıcıdan gelen çağrılar aynı origin'deki proxy'den geçer. Kullanıcıya özel veri Next.js veri önbelleğine yazılmaz (`no-store`), böylece roller arası sızıntı olmaz.
- **Ölçülen:** 750 sporcu, ~4.500 tahakkuk ve 250 lead ile soğuk yanıt **~70 ms**.

## 5. Bilimsel temeller

| Konu | Uygulama | Kaynak |
|---|---|---|
| Antrenman yükü | Seans sonu CR-10 RPE × dakika = sRPE (AU). Rapor ve yoklamada toplanır. | Foster ve ark., 2001, *J Strength Cond Res* 15(1) |
| ACWR **kullanılmıyor** | Akut:kronik oranının sakatlık tahmini istatistiksel olarak sorunlu bulundu. Ham yük trendi gösteriliyor. | Impellizzeri ve ark., 2020, *IJSPP* 15(6) |
| Anlamlı gelişim | Değişim hem SWC'yi (0,2 × grup SD) hem tipik hatayı (TE) aşmıyorsa veliye "gelişti" denmez, "önemsiz/belirsiz" denir. | Hopkins, 2000, *Sports Med* 30(1) |
| Olgunlaşma | Moore 2015 ofseti, PHV öncesi / çevresi / sonrası bio-banding. ±1 yıl hata payı, yalnızca gruplama amaçlı. Altyapıda bağıl yaş etkisine karşı. | Moore ve ark., 2015, *MSSE* 47(8) |
| Maç verimliliği | PIR (EuroLeague), eFG%, TS%. Box score girişinde sayı = 2×İ2 + 3×İ3 + SA kontrolü yapılır. | — |
| Rapor yorumu | Koç yorumu olmadan rapor veliye yayınlanmaz, çünkü bağlamsız sayılar yanlış okunur. | — |
| Lead yanıt hızı | `medianResponseMin` ve `sla-breaches` (varsayılan 15 dk). Hızlı ilk temasın dönüşümü artırdığı pazarlama literatüründe tutarlı bir bulgu; eşik kulübün kendi verisiyle ayarlanmalı. | — |

## 6. Optimizasyon kararları

- **Veritabanı son savunma hattıdır.** `EXCLUDE USING gist` saha ve koç çift rezervasyonunu, eşzamanlı isteklerde bile engeller. CHECK kısıtları ödenen tutarın borcu aşmasını ve geçersiz RPE'yi engeller.
- **Idempotent job'lar.** Tahakkukta `@@unique([subscriptionId, period])`, bildirimlerde `dedupeKey`, webhook'larda `@@unique([provider, externalId])`, ödemelerde `providerTxnId`. İki kez çalışmaları veriyi bozmaz.
- **Job'lar tek süreçte.** `worker` servisi ayrı; API çok worker'la ölçeklense de aidat iki kez kesilmez.
- **N+1 yok.** Aylık rapor tüm kulüp için 3 sorgu, bordro tek toplu sorgu. Kısmi indeksler (`charge_open_due_idx`, `notification_queue_idx`) sıcak sorguları hedefler.
- **Materialized view yok.** Bu ölçekte (~9k tahakkuk/yıl) düz view + indeks yeterli; fazladan karmaşıklık yok.
- **Kilometre taşı zaman damgaları.** Lead'de `firstContactAt`, `trialScheduledAt`, `trialAttendedAt`, `wonAt` tutulur. LOST olan lead'in nereye kadar ilerlediği kaybolmaz ve huni tek `COUNT` ile hesaplanır.
- **Snapshot raporlar.** Yayınlanan aylık rapor sonradan düzeltilen verilerle sessizce değişmez.

## 7. Kurulum

```bash
cd platform
cp .env.example .env          # POSTGRES_PASSWORD, JWT_SECRET, FIELD_ENCRYPTION_KEY zorunlu
docker compose up -d --build
docker compose run --rm api python -m app.seed --athletes 750   # demo verisi
# Panel: http://localhost:3000   API dokümanı: http://localhost:8000/docs (ENV≠production)
# Demo girişi: admin@egealfa.com / EgeAlfa!2026  (finans@, pazarlama@, koc@ da var)
```

Yerel geliştirme:

```bash
cd backend && pip install -r requirements-dev.txt && prisma generate
prisma migrate deploy && python -m app.seed --athletes 750
uvicorn app.main:app --reload
RUN_INTEGRATION=1 pytest            # 30 birim + 9 uçtan uca test

cd ../frontend && npm ci && API_INTERNAL_URL=http://localhost:8000 npm run dev
```

## 8. Doğrulama durumu

- `prisma validate` geçiyor. Migration'lar PostgreSQL 16'ya uygulandı ve şemayla **drift yok**.
- **39/39 test geçiyor:** birim testleri (aidat, FIFO, gecikme kademeleri, bordro, ROI, PIR/eFG/TS, SWC, Moore, İstanbul→UTC çizelgeleme) ve gerçek veritabanında uçtan uca testler (RBAC, haftalık program üretimi + çakışma 409, DB EXCLUDE kısıtı, seans→puantaj, tahakkuk idempotentliği, kısmi ödeme + makbuz, gecikme alarmının tekrar etmemesi, lead→üye dönüşümü, dashboard tutarlılığı ve hızı, veli portalı izolasyonu).
- `ruff` temiz, `tsc --noEmit` temiz, `next build` başarılı. Production bağımlılıklarında `npm audit` 0 açık.
- Dashboard, Playwright ile açık/koyu tema ve mobil genişlikte görsel olarak kontrol edildi.
- CI: `.github/workflows/platform-ci.yml` (PostgreSQL servisiyle tam test + frontend build).

## 9. Açık konular

**Canlıya almadan önce mutlaka:**
1. **Hukuki yapı:** Kulüp dernekse aidat KDV'siz makbuzla (`vatRate=0` → RECEIPT), şirketse e-Arşiv faturayla (%20) işlenir. Mali müşavirle teyit edin; seed'deki planlar KDV'siz.
2. **Paraşüt adaptörü sandbox'ta doğrulanmalı.** Akış Paraşüt API v4 belgelerine göre yazıldı ama gerçek hesapla test edilmedi.
3. **KVKK:** Sporcuların çoğu reşit değil. Veli açık rızası (`Consent`), sağlık verisi ayrı rıza, VERBİS kaydı gerekli. TCKN ve IBAN AES-GCM ile şifreleniyor.
4. **WhatsApp şablonları** (`dues_reminder_soft`, `dues_reminder_link`, `dues_escalation`) Meta Business'ta onaylatılmalı.

**Yol haritası:**
- iyzico kayıtlı kart / otomatik çekim adaptörü
- Google Ads harcama senkronu (şimdilik `/crm/ad-spend/import` ile CSV)
- SMS sağlayıcısı (Netgsm vb.)
- Frontend'in diğer ekranları: yoklama (mobil), haftalık program sürükle-bırak, veli portalı. Bu teslimatta dashboard ve giriş ekranı var.
- Refresh token, giriş için rate limit, PostgreSQL RLS (ikinci savunma hattı)
