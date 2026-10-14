-- ════════════════════════════════════════════════════════════════════════════
--  Prisma'nın ifade edemediği veritabanı garantileri.
--  İş kuralı veritabanında zorlanırsa, hangi istemci (API, worker, psql) yazarsa
--  yazsın tutarsız veri oluşamaz.
-- ════════════════════════════════════════════════════════════════════════════

CREATE EXTENSION IF NOT EXISTS btree_gist;

-- Belge numaraları: boşluksuz değil ama çakışmasız ve eşzamanlılık-güvenli.
-- (e-Arşiv'de nihai seri/sıra no entegratörden döner; bu numara iç referanstır.)
CREATE SEQUENCE invoice_number_seq;
CREATE SEQUENCE receipt_number_seq;

-- ── Takvim: çakışma imkânsız ────────────────────────────────────────────────
ALTER TABLE training_sessions
  ADD CONSTRAINT training_sessions_time_chk CHECK (ends_at > starts_at),
  ADD CONSTRAINT training_sessions_rpe_chk  CHECK (planned_rpe IS NULL OR planned_rpe BETWEEN 1 AND 10);

-- Aynı saha aynı anda iki iptal-edilmemiş seansa verilemez.
ALTER TABLE training_sessions ADD CONSTRAINT training_sessions_no_facility_overlap
  EXCLUDE USING gist (facility_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
  WHERE (status <> 'CANCELLED');

-- Bir koç aynı anda iki seansta olamaz.
ALTER TABLE training_sessions ADD CONSTRAINT training_sessions_no_coach_overlap
  EXCLUDE USING gist (coach_id WITH =, tstzrange(starts_at, ends_at, '[)') WITH &&)
  WHERE (status <> 'CANCELLED');

ALTER TABLE training_plans
  ADD CONSTRAINT training_plans_weekday_chk  CHECK (weekday BETWEEN 1 AND 7),
  ADD CONSTRAINT training_plans_duration_chk CHECK (duration_min BETWEEN 15 AND 240),
  ADD CONSTRAINT training_plans_time_chk     CHECK (start_time ~ '^([01][0-9]|2[0-3]):[0-5][0-9]$');

ALTER TABLE shifts ADD CONSTRAINT shifts_time_chk CHECK (ends_at > starts_at);
ALTER TABLE time_entries
  ADD CONSTRAINT time_entries_time_chk CHECK (clock_out > clock_in),
  ADD CONSTRAINT time_entries_minutes_chk CHECK (minutes >= 0 AND minutes <= 960);

ALTER TABLE attendances
  ADD CONSTRAINT attendances_rpe_chk CHECK (rpe IS NULL OR rpe BETWEEN 0 AND 10),
  ADD CONSTRAINT attendances_minutes_chk CHECK (minutes IS NULL OR minutes >= 0);

-- Bir sporcunun aynı anda tek aktif takım üyeliği olur.
CREATE UNIQUE INDEX team_memberships_one_active
  ON team_memberships (athlete_id) WHERE end_date IS NULL;

-- ── Finans: negatif/tutarsız tutar imkânsız ─────────────────────────────────
ALTER TABLE invoices
  ADD CONSTRAINT invoices_amounts_chk CHECK (subtotal >= 0 AND vat_amount >= 0 AND total = subtotal + vat_amount),
  ADD CONSTRAINT invoices_due_chk     CHECK (due_date >= issue_date),
  ADD CONSTRAINT invoices_paid_chk    CHECK (paid_amount >= 0);
ALTER TABLE payments  ADD CONSTRAINT payments_amount_chk CHECK (amount > 0);
ALTER TABLE expenses  ADD CONSTRAINT expenses_amount_chk CHECK (amount >= 0 AND vat_amount >= 0);
ALTER TABLE fee_plans ADD CONSTRAINT fee_plans_pct_chk
  CHECK (monthly_amount >= 0 AND sibling_discount_pct BETWEEN 0 AND 100 AND vat_rate BETWEEN 0 AND 100);
ALTER TABLE subscriptions
  ADD CONSTRAINT subscriptions_pct_chk CHECK (discount_pct BETWEEN 0 AND 100),
  ADD CONSTRAINT subscriptions_day_chk CHECK (billing_day BETWEEN 1 AND 28);
ALTER TABLE ad_spend_daily ADD CONSTRAINT ad_spend_nonneg_chk CHECK (spend >= 0 AND impressions >= 0 AND clicks >= 0);
ALTER TABLE trial_bookings ADD CONSTRAINT trial_rating_chk CHECK (coach_rating IS NULL OR coach_rating BETWEEN 1 AND 5);

-- Fatura ödenen tutarı ve statüsü tahsilatlardan türetilir (tek yazım noktası).
CREATE OR REPLACE FUNCTION refresh_invoice_paid() RETURNS trigger AS $$
DECLARE inv_id int;
BEGIN
  FOR inv_id IN SELECT DISTINCT x FROM unnest(ARRAY[
      CASE WHEN TG_OP <> 'INSERT' THEN OLD.invoice_id END,
      CASE WHEN TG_OP <> 'DELETE' THEN NEW.invoice_id END]) AS x WHERE x IS NOT NULL
  LOOP
    UPDATE invoices i SET
      paid_amount = p.paid,
      status = CASE
        WHEN i.status IN ('CANCELLED','DRAFT') THEN i.status
        WHEN p.paid >= i.total THEN 'PAID'::invoice_status
        WHEN p.paid > 0        THEN 'PARTIALLY_PAID'::invoice_status
        ELSE 'ISSUED'::invoice_status END
    FROM (SELECT COALESCE(SUM(amount),0) AS paid FROM payments WHERE invoice_id = inv_id) p
    WHERE i.id = inv_id;
  END LOOP;
  RETURN NULL;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER payments_refresh_invoice
AFTER INSERT OR UPDATE OF amount, invoice_id OR DELETE ON payments
FOR EACH ROW EXECUTE FUNCTION refresh_invoice_paid();

-- ── Görünümler (analitik) ───────────────────────────────────────────────────
-- Açık bakiye + gecikme günü: "gecikmiş" statüsü depolanmaz, hesaplanır.
CREATE VIEW v_invoice_balance AS
SELECT i.id, i.number, i.guardian_id, i.athlete_id, i.period, i.issue_date, i.due_date,
       i.total, i.paid_amount, (i.total - i.paid_amount) AS balance, i.status,
       GREATEST(CURRENT_DATE - i.due_date, 0) AS days_overdue,
       (i.status IN ('ISSUED','PARTIALLY_PAID') AND i.due_date < CURRENT_DATE) AS is_overdue
FROM invoices i
WHERE i.status NOT IN ('CANCELLED','DRAFT');

-- Kasa hareketleri: tahakkuk değil nakit esaslı gelir-gider.
CREATE VIEW v_cash_movements AS
SELECT paid_at::date AS day, 'INCOME'::text AS direction, 'TUITION'::text AS category, amount
FROM payments
UNION ALL
SELECT spent_at, 'EXPENSE', category::text, amount FROM expenses
UNION ALL
SELECT paid_at::date, 'EXPENSE', 'PAYROLL', employer_cost FROM payrolls WHERE status = 'PAID';

CREATE VIEW v_athlete_current_team AS
SELECT DISTINCT ON (m.athlete_id) m.athlete_id, m.team_id, t.name AS team_name, t.age_group, t.head_coach_id
FROM team_memberships m JOIN teams t ON t.id = m.team_id
WHERE m.end_date IS NULL
ORDER BY m.athlete_id, m.start_date DESC;
