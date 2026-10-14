-- Prisma şemasının ifade edemediği bütünlük kuralları.
-- Bu kurallar uygulama katmanında da kontrol edilir; ama son savunma hattı veritabanıdır.

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- ── Zaman tutarlılığı ────────────────────────────────────────────────────────
ALTER TABLE "TrainingSession" ADD CONSTRAINT "session_time_ck" CHECK ("endsAt" > "startsAt");
ALTER TABLE "Shift"           ADD CONSTRAINT "shift_time_ck"   CHECK ("endsAt" > "startsAt");
ALTER TABLE "RecurringSlot"   ADD CONSTRAINT "slot_weekday_ck" CHECK ("weekday" BETWEEN 0 AND 6);
ALTER TABLE "RecurringSlot"   ADD CONSTRAINT "slot_time_ck"    CHECK ("endTime" > "startTime");

-- ── Saha ve koç çift rezervasyon koruması ───────────────────────────────────
-- İptal edilmemiş iki seans aynı sahada / aynı koçta zaman olarak çakışamaz.
-- Büyük salon ikiye bölünüyorsa iki ayrı Court kaydı açılır ("Salon A - Yarı 1/2").
ALTER TABLE "TrainingSession" ADD CONSTRAINT "session_court_no_overlap"
  EXCLUDE USING gist (
    "courtId" WITH =,
    tsrange("startsAt", "endsAt", '[)') WITH &&
  ) WHERE ("status" <> 'CANCELLED');

ALTER TABLE "TrainingSession" ADD CONSTRAINT "session_coach_no_overlap"
  EXCLUDE USING gist (
    "coachId" WITH =,
    tsrange("startsAt", "endsAt", '[)') WITH &&
  ) WHERE ("status" <> 'CANCELLED');

-- ── Finans bütünlüğü ────────────────────────────────────────────────────────
ALTER TABLE "Charge" ADD CONSTRAINT "charge_amounts_ck" CHECK (
  "grossAmount" >= 0 AND "discountAmount" >= 0 AND "netAmount" >= 0
  AND "paidAmount" >= 0 AND "paidAmount" <= "netAmount"
);
ALTER TABLE "Payment"           ADD CONSTRAINT "payment_amount_ck"    CHECK ("amount" > 0);
ALTER TABLE "PaymentAllocation" ADD CONSTRAINT "allocation_amount_ck" CHECK ("amount" > 0);
ALTER TABLE "Expense"           ADD CONSTRAINT "expense_amount_ck"    CHECK ("amount" >= 0);
ALTER TABLE "Subscription"      ADD CONSTRAINT "sub_discount_ck"      CHECK ("discountPct" BETWEEN 0 AND 100);

-- ── Sporcu verisi ───────────────────────────────────────────────────────────
ALTER TABLE "Attendance"   ADD CONSTRAINT "attendance_rpe_ck"   CHECK ("rpe" IS NULL OR "rpe" BETWEEN 0 AND 10);
ALTER TABLE "TrialBooking" ADD CONSTRAINT "trial_rating_ck"     CHECK ("coachRating" IS NULL OR "coachRating" BETWEEN 1 AND 5);

-- ── Sıcak sorgular için kısmi indeksler ─────────────────────────────────────
-- Gecikme alarmı job'u yalnızca açık borçları tarar.
CREATE INDEX "charge_open_due_idx" ON "Charge" ("dueDate")
  WHERE "status" IN ('PENDING', 'PARTIALLY_PAID', 'OVERDUE');

-- Notification worker kuyruğu.
CREATE INDEX "notification_queue_idx" ON "Notification" ("scheduledFor")
  WHERE "status" = 'QUEUED';

-- ── Raporlama görünümleri ───────────────────────────────────────────────────
-- 750 sporcu ölçeğinde (~9k tahakkuk/yıl) düz view yeterli; materialized view gereksiz karmaşa.

-- Aylık gelir-gider (nakit esaslı). Reklam harcaması AdSpendDaily'den gelir,
-- Expense'e ayrıca girilmez (çift sayım koruması).
CREATE VIEW "v_monthly_cashflow" AS
WITH inc AS (
  SELECT date_trunc('month', "paidAt")::date AS month, SUM("amount") AS income
  FROM "Payment" WHERE "status" = 'COMPLETED'
  GROUP BY 1
), exp AS (
  SELECT date_trunc('month', "incurredOn")::date AS month, SUM("amount") AS expense
  FROM "Expense"
  GROUP BY 1
), ads AS (
  SELECT date_trunc('month', "date")::date AS month, SUM("spend") AS ad_spend
  FROM "AdSpendDaily"
  GROUP BY 1
), months AS (
  SELECT month FROM inc UNION SELECT month FROM exp UNION SELECT month FROM ads
)
SELECT m.month,
       COALESCE(inc.income, 0)   AS income,
       COALESCE(exp.expense, 0)  AS expense,
       COALESCE(ads.ad_spend, 0) AS ad_spend,
       COALESCE(inc.income, 0) - COALESCE(exp.expense, 0) - COALESCE(ads.ad_spend, 0) AS net
FROM months m
LEFT JOIN inc ON inc.month = m.month
LEFT JOIN exp ON exp.month = m.month
LEFT JOIN ads ON ads.month = m.month;

-- Lead → kampanya → kazanılan sporcunun tahsil edilen geliri (first-touch atıf).
CREATE VIEW "v_lead_revenue" AS
SELECT l."id" AS lead_id, l."campaignId" AS campaign_id, l."source" AS source,
       l."convertedAthleteId" AS athlete_id, pay."paidAt" AS paid_at, pa."amount" AS amount
FROM "Lead" l
JOIN "Charge" c             ON c."athleteId" = l."convertedAthleteId"
JOIN "PaymentAllocation" pa ON pa."chargeId" = c."id"
JOIN "Payment" pay          ON pay."id" = pa."paymentId" AND pay."status" = 'COMPLETED'
WHERE l."convertedAthleteId" IS NOT NULL;
