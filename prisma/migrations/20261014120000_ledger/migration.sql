-- CreateEnum
CREATE TYPE "ledger_kind" AS ENUM ('MONTHLY', 'PARTIAL', 'MULTI_MONTH', 'SEASON_UPFRONT', 'SEASON_INSTALLMENT', 'TEXTILE', 'EVENT', 'ARREARS', 'OTHER');

-- CreateTable
CREATE TABLE "ledger_imports" (
    "id" SERIAL NOT NULL,
    "file_name" TEXT NOT NULL,
    "sha256" TEXT NOT NULL,
    "sheets" TEXT[],
    "row_count" INTEGER NOT NULL,
    "anomalies" JSONB NOT NULL,
    "imported_by" INTEGER,
    "imported_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ledger_imports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ledger_entries" (
    "id" BIGSERIAL NOT NULL,
    "import_id" INTEGER NOT NULL,
    "sheet" TEXT NOT NULL,
    "source_row" INTEGER NOT NULL,
    "sheet_month" DATE NOT NULL,
    "paid_on" DATE NOT NULL,
    "paid_on_inferred" BOOLEAN NOT NULL,
    "player_name" TEXT NOT NULL,
    "player_key" TEXT NOT NULL,
    "multi_player" BOOLEAN NOT NULL DEFAULT false,
    "athlete_id" INTEGER,
    "group" TEXT NOT NULL,
    "period_label" TEXT NOT NULL,
    "kind" "ledger_kind" NOT NULL,
    "covered_months" DATE[],
    "scholarship" BOOLEAN NOT NULL DEFAULT false,
    "amount" DECIMAL(12,2) NOT NULL,
    "dues_amount" DECIMAL(12,2) NOT NULL,
    "textile_amount" DECIMAL(12,2) NOT NULL,
    "channel_raw" TEXT NOT NULL,
    "channel" TEXT NOT NULL,
    "method" "payment_method" NOT NULL,
    "cancelled" BOOLEAN NOT NULL DEFAULT false,
    "note" TEXT,

    CONSTRAINT "ledger_entries_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ledger_entries_sheet_month_idx" ON "ledger_entries"("sheet_month");

-- CreateIndex
CREATE INDEX "ledger_entries_player_key_idx" ON "ledger_entries"("player_key");

-- CreateIndex
CREATE UNIQUE INDEX "ledger_entries_sheet_source_row_key" ON "ledger_entries"("sheet", "source_row");

-- AddForeignKey
ALTER TABLE "ledger_entries" ADD CONSTRAINT "ledger_entries_import_id_fkey" FOREIGN KEY ("import_id") REFERENCES "ledger_imports"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ledger_entries" ADD CONSTRAINT "ledger_entries_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE SET NULL ON UPDATE CASCADE;


-- ── Defter tutarlılığı ──────────────────────────────────────────────────────
ALTER TABLE ledger_entries
  ADD CONSTRAINT ledger_amount_chk CHECK (amount > 0 AND dues_amount >= 0 AND textile_amount >= 0
                                          AND dues_amount + textile_amount = amount);
ALTER TABLE seasons ADD CONSTRAINT seasons_range_chk CHECK (end_date > start_date);

-- Defter tahsilatları nakit akışına girer (iptal edilenler hariç). Canlı tahsilata
-- geçildiği aydan sonra Excel defteri içe aktarılmamalıdır (çift sayım).
CREATE OR REPLACE VIEW v_cash_movements AS
SELECT paid_at::date AS day, 'INCOME'::text AS direction, 'TUITION'::text AS category, amount
FROM payments
UNION ALL
SELECT spent_at, 'EXPENSE', category::text, amount FROM expenses
UNION ALL
SELECT paid_at::date, 'EXPENSE', 'PAYROLL', employer_cost FROM payrolls WHERE status = 'PAID'
UNION ALL
SELECT paid_on, 'INCOME', CASE WHEN kind = 'EVENT' THEN 'LEDGER_EVENT' ELSE 'LEDGER_DUES' END, dues_amount
FROM ledger_entries WHERE NOT cancelled AND dues_amount > 0
UNION ALL
SELECT paid_on, 'INCOME', 'LEDGER_TEXTILE', textile_amount
FROM ledger_entries WHERE NOT cancelled AND textile_amount > 0;
