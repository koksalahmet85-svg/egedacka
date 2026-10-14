-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateEnum
CREATE TYPE "role" AS ENUM ('ADMIN', 'MANAGER', 'COACH', 'ACCOUNTANT', 'MARKETING', 'GUARDIAN');

-- CreateEnum
CREATE TYPE "department" AS ENUM ('COACHING', 'ADMINISTRATION', 'MARKETING', 'FINANCE', 'OPERATIONS');

-- CreateEnum
CREATE TYPE "employment_type" AS ENUM ('FULL_TIME', 'PART_TIME', 'HOURLY');

-- CreateEnum
CREATE TYPE "facility_type" AS ENUM ('COURT', 'GYM', 'CONDITIONING', 'CLASSROOM');

-- CreateEnum
CREATE TYPE "shift_type" AS ENUM ('TRAINING', 'ADMIN_DESK', 'EVENT', 'GAME_DAY');

-- CreateEnum
CREATE TYPE "time_entry_source" AS ENUM ('SESSION_AUTO', 'QR_CHECKIN', 'MANUAL');

-- CreateEnum
CREATE TYPE "timesheet_status" AS ENUM ('DRAFT', 'APPROVED', 'LOCKED');

-- CreateEnum
CREATE TYPE "team_level" AS ENUM ('SCHOOL', 'DEVELOPMENT', 'PERFORMANCE');

-- CreateEnum
CREATE TYPE "gender" AS ENUM ('MALE', 'FEMALE');

-- CreateEnum
CREATE TYPE "athlete_status" AS ENUM ('TRIAL', 'ACTIVE', 'FROZEN', 'LEFT');

-- CreateEnum
CREATE TYPE "session_type" AS ENUM ('TEAM', 'INDIVIDUAL', 'STRENGTH_CONDITIONING', 'GAME', 'TRIAL');

-- CreateEnum
CREATE TYPE "session_status" AS ENUM ('PLANNED', 'COMPLETED', 'CANCELLED');

-- CreateEnum
CREATE TYPE "attendance_status" AS ENUM ('PRESENT', 'LATE', 'EXCUSED', 'ABSENT', 'INJURED');

-- CreateEnum
CREATE TYPE "metric_category" AS ENUM ('ANTHROPOMETRIC', 'ATHLETIC', 'FUNDAMENTAL', 'WELLNESS');

-- CreateEnum
CREATE TYPE "invoice_status" AS ENUM ('DRAFT', 'ISSUED', 'PARTIALLY_PAID', 'PAID', 'CANCELLED');

-- CreateEnum
CREATE TYPE "earchive_status" AS ENUM ('NOT_SENT', 'QUEUED', 'ACCEPTED', 'REJECTED');

-- CreateEnum
CREATE TYPE "payment_method" AS ENUM ('CASH', 'BANK_TRANSFER', 'CREDIT_CARD', 'ONLINE');

-- CreateEnum
CREATE TYPE "reminder_level" AS ENUM ('DUE_SOON', 'OVERDUE_1', 'OVERDUE_7', 'OVERDUE_15', 'OVERDUE_30');

-- CreateEnum
CREATE TYPE "payroll_status" AS ENUM ('DRAFT', 'APPROVED', 'PAID');

-- CreateEnum
CREATE TYPE "expense_category" AS ENUM ('FACILITY_RENT', 'EQUIPMENT', 'TRAVEL', 'LEAGUE_FEES', 'MARKETING', 'UTILITIES', 'TAX', 'OTHER');

-- CreateEnum
CREATE TYPE "channel" AS ENUM ('META_ADS', 'GOOGLE_ADS', 'TIKTOK_ADS', 'ORGANIC_SOCIAL', 'WEBSITE', 'REFERRAL', 'SCHOOL_EVENT', 'WALK_IN');

-- CreateEnum
CREATE TYPE "lead_stage" AS ENUM ('NEW', 'CONTACTED', 'TRIAL_SCHEDULED', 'TRIAL_ATTENDED', 'WON', 'LOST');

-- CreateEnum
CREATE TYPE "activity_type" AS ENUM ('CALL', 'WHATSAPP', 'SMS', 'EMAIL', 'NOTE', 'STAGE_CHANGE');

-- CreateEnum
CREATE TYPE "trial_status" AS ENUM ('BOOKED', 'ATTENDED', 'NO_SHOW', 'CANCELLED');

-- CreateEnum
CREATE TYPE "outbox_status" AS ENUM ('PENDING', 'SENT', 'FAILED');

-- CreateTable
CREATE TABLE "users" (
    "id" SERIAL NOT NULL,
    "email" TEXT NOT NULL,
    "password_hash" TEXT NOT NULL,
    "role" "role" NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT true,
    "last_login_at" TIMESTAMPTZ(3),
    "staff_id" INTEGER,
    "guardian_id" INTEGER,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "audit_logs" (
    "id" BIGSERIAL NOT NULL,
    "user_id" INTEGER,
    "action" TEXT NOT NULL,
    "entity" TEXT NOT NULL,
    "entity_id" TEXT NOT NULL,
    "diff" JSONB,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "audit_logs_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "staff" (
    "id" SERIAL NOT NULL,
    "first_name" TEXT NOT NULL,
    "last_name" TEXT NOT NULL,
    "phone" TEXT,
    "email" TEXT,
    "department" "department" NOT NULL,
    "title" TEXT NOT NULL,
    "employment_type" "employment_type" NOT NULL,
    "monthly_salary" DECIMAL(12,2),
    "hourly_rate" DECIMAL(10,2),
    "coach_license" TEXT,
    "iban_encrypted" TEXT,
    "hire_date" DATE NOT NULL,
    "terminated_at" DATE,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "staff_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "facilities" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "type" "facility_type" NOT NULL,
    "capacity" INTEGER NOT NULL,
    "hourly_cost" DECIMAL(10,2) NOT NULL DEFAULT 0,
    "address" TEXT,
    "is_active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "facilities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "shifts" (
    "id" SERIAL NOT NULL,
    "staff_id" INTEGER NOT NULL,
    "facility_id" INTEGER,
    "type" "shift_type" NOT NULL,
    "starts_at" TIMESTAMPTZ(3) NOT NULL,
    "ends_at" TIMESTAMPTZ(3) NOT NULL,
    "note" TEXT,

    CONSTRAINT "shifts_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "time_entries" (
    "id" SERIAL NOT NULL,
    "staff_id" INTEGER NOT NULL,
    "session_id" INTEGER,
    "clock_in" TIMESTAMPTZ(3) NOT NULL,
    "clock_out" TIMESTAMPTZ(3) NOT NULL,
    "minutes" INTEGER NOT NULL,
    "source" "time_entry_source" NOT NULL,
    "approved_by_id" INTEGER,
    "approved_at" TIMESTAMPTZ(3),
    "timesheet_id" INTEGER,

    CONSTRAINT "time_entries_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "timesheets" (
    "id" SERIAL NOT NULL,
    "staff_id" INTEGER NOT NULL,
    "period" DATE NOT NULL,
    "total_minutes" INTEGER NOT NULL DEFAULT 0,
    "session_count" INTEGER NOT NULL DEFAULT 0,
    "status" "timesheet_status" NOT NULL DEFAULT 'DRAFT',

    CONSTRAINT "timesheets_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "seasons" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "start_date" DATE NOT NULL,
    "end_date" DATE NOT NULL,
    "is_active" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "seasons_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "teams" (
    "id" SERIAL NOT NULL,
    "season_id" INTEGER NOT NULL,
    "name" TEXT NOT NULL,
    "age_group" TEXT NOT NULL,
    "level" "team_level" NOT NULL,
    "head_coach_id" INTEGER,
    "max_athletes" INTEGER NOT NULL DEFAULT 15,
    "default_fee_plan_id" INTEGER,

    CONSTRAINT "teams_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "team_coaches" (
    "team_id" INTEGER NOT NULL,
    "staff_id" INTEGER NOT NULL,
    "role" TEXT NOT NULL DEFAULT 'ASSISTANT',

    CONSTRAINT "team_coaches_pkey" PRIMARY KEY ("team_id","staff_id")
);

-- CreateTable
CREATE TABLE "athletes" (
    "id" SERIAL NOT NULL,
    "first_name" TEXT NOT NULL,
    "last_name" TEXT NOT NULL,
    "birth_date" DATE NOT NULL,
    "gender" "gender" NOT NULL,
    "status" "athlete_status" NOT NULL DEFAULT 'ACTIVE',
    "position" TEXT,
    "license_no" TEXT,
    "health_report_expires_at" DATE,
    "photo_consent" BOOLEAN NOT NULL DEFAULT false,
    "joined_at" DATE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "left_at" DATE,
    "left_reason" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "athletes_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "guardians" (
    "id" SERIAL NOT NULL,
    "full_name" TEXT NOT NULL,
    "phone" TEXT NOT NULL,
    "email" TEXT,
    "tax_id_encrypted" TEXT,
    "address" TEXT,
    "kvkk_consent_at" TIMESTAMPTZ(3),
    "marketing_consent_at" TIMESTAMPTZ(3),
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "guardians_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "athlete_guardians" (
    "athlete_id" INTEGER NOT NULL,
    "guardian_id" INTEGER NOT NULL,
    "relation" TEXT NOT NULL,
    "is_primary" BOOLEAN NOT NULL DEFAULT false,

    CONSTRAINT "athlete_guardians_pkey" PRIMARY KEY ("athlete_id","guardian_id")
);

-- CreateTable
CREATE TABLE "team_memberships" (
    "id" SERIAL NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "team_id" INTEGER NOT NULL,
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "jersey" INTEGER,

    CONSTRAINT "team_memberships_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "training_plans" (
    "id" SERIAL NOT NULL,
    "team_id" INTEGER NOT NULL,
    "coach_id" INTEGER NOT NULL,
    "facility_id" INTEGER NOT NULL,
    "weekday" INTEGER NOT NULL,
    "start_time" TEXT NOT NULL,
    "duration_min" INTEGER NOT NULL,
    "valid_from" DATE NOT NULL,
    "valid_to" DATE,
    "focus" TEXT,

    CONSTRAINT "training_plans_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "training_sessions" (
    "id" SERIAL NOT NULL,
    "plan_id" INTEGER,
    "team_id" INTEGER,
    "coach_id" INTEGER NOT NULL,
    "facility_id" INTEGER NOT NULL,
    "type" "session_type" NOT NULL DEFAULT 'TEAM',
    "status" "session_status" NOT NULL DEFAULT 'PLANNED',
    "starts_at" TIMESTAMPTZ(3) NOT NULL,
    "ends_at" TIMESTAMPTZ(3) NOT NULL,
    "focus" TEXT,
    "planned_rpe" INTEGER,
    "notes" TEXT,
    "cancel_reason" TEXT,

    CONSTRAINT "training_sessions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "drills" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "category" TEXT NOT NULL,
    "description" TEXT,
    "video_url" TEXT,
    "min_age_group" TEXT,

    CONSTRAINT "drills_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "session_blocks" (
    "id" SERIAL NOT NULL,
    "session_id" INTEGER NOT NULL,
    "drill_id" INTEGER,
    "order" INTEGER NOT NULL,
    "duration_min" INTEGER NOT NULL,
    "notes" TEXT,

    CONSTRAINT "session_blocks_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "attendances" (
    "session_id" INTEGER NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "status" "attendance_status" NOT NULL,
    "rpe" INTEGER,
    "minutes" INTEGER,
    "recorded_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "attendances_pkey" PRIMARY KEY ("session_id","athlete_id")
);

-- CreateTable
CREATE TABLE "metric_definitions" (
    "id" SERIAL NOT NULL,
    "code" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "unit" TEXT NOT NULL,
    "category" "metric_category" NOT NULL,
    "higher_is_better" BOOLEAN NOT NULL,
    "typical_error" DECIMAL(8,3),

    CONSTRAINT "metric_definitions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "assessments" (
    "id" SERIAL NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "assessor_id" INTEGER,
    "assessed_at" DATE NOT NULL,
    "context" TEXT,
    "coach_note" TEXT,

    CONSTRAINT "assessments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "measurements" (
    "id" SERIAL NOT NULL,
    "assessment_id" INTEGER NOT NULL,
    "metric_id" INTEGER NOT NULL,
    "value" DECIMAL(10,3) NOT NULL,

    CONSTRAINT "measurements_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "games" (
    "id" SERIAL NOT NULL,
    "team_id" INTEGER NOT NULL,
    "opponent" TEXT NOT NULL,
    "played_at" TIMESTAMPTZ(3) NOT NULL,
    "is_home" BOOLEAN NOT NULL,
    "competition" TEXT,
    "score_for" INTEGER,
    "score_against" INTEGER,

    CONSTRAINT "games_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "game_stats" (
    "game_id" INTEGER NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "minutes" INTEGER NOT NULL DEFAULT 0,
    "pts" INTEGER NOT NULL DEFAULT 0,
    "fgm" INTEGER NOT NULL DEFAULT 0,
    "fga" INTEGER NOT NULL DEFAULT 0,
    "tpm" INTEGER NOT NULL DEFAULT 0,
    "tpa" INTEGER NOT NULL DEFAULT 0,
    "ftm" INTEGER NOT NULL DEFAULT 0,
    "fta" INTEGER NOT NULL DEFAULT 0,
    "oreb" INTEGER NOT NULL DEFAULT 0,
    "dreb" INTEGER NOT NULL DEFAULT 0,
    "ast" INTEGER NOT NULL DEFAULT 0,
    "stl" INTEGER NOT NULL DEFAULT 0,
    "blk" INTEGER NOT NULL DEFAULT 0,
    "tov" INTEGER NOT NULL DEFAULT 0,
    "pf" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "game_stats_pkey" PRIMARY KEY ("game_id","athlete_id")
);

-- CreateTable
CREATE TABLE "performance_reports" (
    "id" SERIAL NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "period" DATE NOT NULL,
    "summary" JSONB NOT NULL,
    "coach_note" TEXT,
    "published_at" TIMESTAMPTZ(3),
    "pdf_url" TEXT,

    CONSTRAINT "performance_reports_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "fee_plans" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "monthly_amount" DECIMAL(12,2) NOT NULL,
    "vat_rate" DECIMAL(5,2) NOT NULL DEFAULT 20,
    "sibling_discount_pct" DECIMAL(5,2) NOT NULL DEFAULT 10,
    "is_active" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "fee_plans_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "subscriptions" (
    "id" SERIAL NOT NULL,
    "athlete_id" INTEGER NOT NULL,
    "guardian_id" INTEGER NOT NULL,
    "fee_plan_id" INTEGER NOT NULL,
    "discount_pct" DECIMAL(5,2) NOT NULL DEFAULT 0,
    "discount_reason" TEXT,
    "billing_day" INTEGER NOT NULL DEFAULT 1,
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "paused_until" DATE,

    CONSTRAINT "subscriptions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoices" (
    "id" SERIAL NOT NULL,
    "number" TEXT NOT NULL,
    "subscription_id" INTEGER,
    "guardian_id" INTEGER NOT NULL,
    "athlete_id" INTEGER,
    "period" DATE,
    "issue_date" DATE NOT NULL,
    "due_date" DATE NOT NULL,
    "subtotal" DECIMAL(12,2) NOT NULL,
    "vat_amount" DECIMAL(12,2) NOT NULL,
    "total" DECIMAL(12,2) NOT NULL,
    "paid_amount" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "status" "invoice_status" NOT NULL DEFAULT 'ISSUED',
    "earchive_status" "earchive_status" NOT NULL DEFAULT 'NOT_SENT',
    "earchive_uuid" TEXT,
    "pdf_url" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "invoices_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "invoice_lines" (
    "id" SERIAL NOT NULL,
    "invoice_id" INTEGER NOT NULL,
    "description" TEXT NOT NULL,
    "quantity" DECIMAL(10,2) NOT NULL DEFAULT 1,
    "unit_price" DECIMAL(12,2) NOT NULL,
    "discount" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "vat_rate" DECIMAL(5,2) NOT NULL,
    "line_total" DECIMAL(12,2) NOT NULL,

    CONSTRAINT "invoice_lines_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payments" (
    "id" SERIAL NOT NULL,
    "invoice_id" INTEGER,
    "guardian_id" INTEGER NOT NULL,
    "amount" DECIMAL(12,2) NOT NULL,
    "method" "payment_method" NOT NULL,
    "paid_at" TIMESTAMPTZ(3) NOT NULL,
    "receipt_no" TEXT NOT NULL,
    "provider_ref" TEXT,
    "note" TEXT,
    "recorded_by_id" INTEGER,

    CONSTRAINT "payments_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payment_reminders" (
    "id" SERIAL NOT NULL,
    "invoice_id" INTEGER NOT NULL,
    "level" "reminder_level" NOT NULL,
    "channel" TEXT NOT NULL,
    "sent_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "payment_reminders_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "payrolls" (
    "id" SERIAL NOT NULL,
    "staff_id" INTEGER NOT NULL,
    "period" DATE NOT NULL,
    "timesheet_id" INTEGER,
    "base_gross" DECIMAL(12,2) NOT NULL,
    "hourly_gross" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "bonus" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "deductions" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "net_pay" DECIMAL(12,2),
    "employer_cost" DECIMAL(12,2) NOT NULL,
    "status" "payroll_status" NOT NULL DEFAULT 'DRAFT',
    "paid_at" TIMESTAMPTZ(3),

    CONSTRAINT "payrolls_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "expenses" (
    "id" SERIAL NOT NULL,
    "category" "expense_category" NOT NULL,
    "amount" DECIMAL(12,2) NOT NULL,
    "vat_amount" DECIMAL(12,2) NOT NULL DEFAULT 0,
    "spent_at" DATE NOT NULL,
    "vendor" TEXT,
    "description" TEXT,
    "document_url" TEXT,
    "campaign_id" INTEGER,

    CONSTRAINT "expenses_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "campaigns" (
    "id" SERIAL NOT NULL,
    "name" TEXT NOT NULL,
    "channel" "channel" NOT NULL,
    "external_id" TEXT,
    "start_date" DATE NOT NULL,
    "end_date" DATE,
    "budget" DECIMAL(12,2),
    "target_age_group" TEXT,

    CONSTRAINT "campaigns_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ad_spend_daily" (
    "campaign_id" INTEGER NOT NULL,
    "date" DATE NOT NULL,
    "spend" DECIMAL(12,2) NOT NULL,
    "impressions" INTEGER NOT NULL DEFAULT 0,
    "clicks" INTEGER NOT NULL DEFAULT 0,
    "platform_leads" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "ad_spend_daily_pkey" PRIMARY KEY ("campaign_id","date")
);

-- CreateTable
CREATE TABLE "leads" (
    "id" SERIAL NOT NULL,
    "child_name" TEXT NOT NULL,
    "child_birth_year" INTEGER,
    "guardian_name" TEXT NOT NULL,
    "phone" TEXT NOT NULL,
    "email" TEXT,
    "channel" "channel" NOT NULL,
    "campaign_id" INTEGER,
    "external_lead_id" TEXT,
    "utm_source" TEXT,
    "utm_medium" TEXT,
    "utm_campaign" TEXT,
    "utm_content" TEXT,
    "click_id" TEXT,
    "stage" "lead_stage" NOT NULL DEFAULT 'NEW',
    "lost_reason" TEXT,
    "owner_id" INTEGER,
    "kvkk_consent_at" TIMESTAMPTZ(3),
    "first_contact_at" TIMESTAMPTZ(3),
    "converted_at" TIMESTAMPTZ(3),
    "athlete_id" INTEGER,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "leads_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "lead_activities" (
    "id" SERIAL NOT NULL,
    "lead_id" INTEGER NOT NULL,
    "type" "activity_type" NOT NULL,
    "from_stage" "lead_stage",
    "to_stage" "lead_stage",
    "note" TEXT,
    "staff_id" INTEGER,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "lead_activities_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "trial_bookings" (
    "id" SERIAL NOT NULL,
    "lead_id" INTEGER NOT NULL,
    "session_id" INTEGER NOT NULL,
    "status" "trial_status" NOT NULL DEFAULT 'BOOKED',
    "coach_feedback" TEXT,
    "coach_rating" INTEGER,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "trial_bookings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "notification_outbox" (
    "id" BIGSERIAL NOT NULL,
    "channel" TEXT NOT NULL,
    "recipient" TEXT NOT NULL,
    "template" TEXT NOT NULL,
    "payload" JSONB NOT NULL,
    "dedupe_key" TEXT NOT NULL,
    "status" "outbox_status" NOT NULL DEFAULT 'PENDING',
    "attempts" INTEGER NOT NULL DEFAULT 0,
    "last_error" TEXT,
    "created_at" TIMESTAMPTZ(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "sent_at" TIMESTAMPTZ(3),

    CONSTRAINT "notification_outbox_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "users_email_key" ON "users"("email");

-- CreateIndex
CREATE UNIQUE INDEX "users_staff_id_key" ON "users"("staff_id");

-- CreateIndex
CREATE UNIQUE INDEX "users_guardian_id_key" ON "users"("guardian_id");

-- CreateIndex
CREATE INDEX "audit_logs_entity_entity_id_idx" ON "audit_logs"("entity", "entity_id");

-- CreateIndex
CREATE INDEX "audit_logs_created_at_idx" ON "audit_logs"("created_at");

-- CreateIndex
CREATE UNIQUE INDEX "staff_email_key" ON "staff"("email");

-- CreateIndex
CREATE INDEX "staff_department_idx" ON "staff"("department");

-- CreateIndex
CREATE UNIQUE INDEX "facilities_name_key" ON "facilities"("name");

-- CreateIndex
CREATE INDEX "shifts_staff_id_starts_at_idx" ON "shifts"("staff_id", "starts_at");

-- CreateIndex
CREATE UNIQUE INDEX "time_entries_session_id_key" ON "time_entries"("session_id");

-- CreateIndex
CREATE INDEX "time_entries_staff_id_clock_in_idx" ON "time_entries"("staff_id", "clock_in");

-- CreateIndex
CREATE UNIQUE INDEX "timesheets_staff_id_period_key" ON "timesheets"("staff_id", "period");

-- CreateIndex
CREATE UNIQUE INDEX "seasons_name_key" ON "seasons"("name");

-- CreateIndex
CREATE UNIQUE INDEX "teams_season_id_name_key" ON "teams"("season_id", "name");

-- CreateIndex
CREATE UNIQUE INDEX "athletes_license_no_key" ON "athletes"("license_no");

-- CreateIndex
CREATE INDEX "athletes_status_idx" ON "athletes"("status");

-- CreateIndex
CREATE INDEX "athletes_last_name_first_name_idx" ON "athletes"("last_name", "first_name");

-- CreateIndex
CREATE UNIQUE INDEX "guardians_phone_key" ON "guardians"("phone");

-- CreateIndex
CREATE INDEX "athlete_guardians_guardian_id_idx" ON "athlete_guardians"("guardian_id");

-- CreateIndex
CREATE INDEX "team_memberships_team_id_end_date_idx" ON "team_memberships"("team_id", "end_date");

-- CreateIndex
CREATE INDEX "team_memberships_athlete_id_end_date_idx" ON "team_memberships"("athlete_id", "end_date");

-- CreateIndex
CREATE INDEX "training_plans_team_id_idx" ON "training_plans"("team_id");

-- CreateIndex
CREATE INDEX "training_sessions_starts_at_idx" ON "training_sessions"("starts_at");

-- CreateIndex
CREATE INDEX "training_sessions_team_id_starts_at_idx" ON "training_sessions"("team_id", "starts_at");

-- CreateIndex
CREATE INDEX "training_sessions_coach_id_starts_at_idx" ON "training_sessions"("coach_id", "starts_at");

-- CreateIndex
CREATE UNIQUE INDEX "training_sessions_plan_id_starts_at_key" ON "training_sessions"("plan_id", "starts_at");

-- CreateIndex
CREATE UNIQUE INDEX "drills_name_key" ON "drills"("name");

-- CreateIndex
CREATE UNIQUE INDEX "session_blocks_session_id_order_key" ON "session_blocks"("session_id", "order");

-- CreateIndex
CREATE INDEX "attendances_athlete_id_idx" ON "attendances"("athlete_id");

-- CreateIndex
CREATE UNIQUE INDEX "metric_definitions_code_key" ON "metric_definitions"("code");

-- CreateIndex
CREATE INDEX "assessments_athlete_id_assessed_at_idx" ON "assessments"("athlete_id", "assessed_at");

-- CreateIndex
CREATE INDEX "measurements_metric_id_idx" ON "measurements"("metric_id");

-- CreateIndex
CREATE UNIQUE INDEX "measurements_assessment_id_metric_id_key" ON "measurements"("assessment_id", "metric_id");

-- CreateIndex
CREATE INDEX "games_team_id_played_at_idx" ON "games"("team_id", "played_at");

-- CreateIndex
CREATE INDEX "game_stats_athlete_id_idx" ON "game_stats"("athlete_id");

-- CreateIndex
CREATE UNIQUE INDEX "performance_reports_athlete_id_period_key" ON "performance_reports"("athlete_id", "period");

-- CreateIndex
CREATE UNIQUE INDEX "fee_plans_name_key" ON "fee_plans"("name");

-- CreateIndex
CREATE INDEX "subscriptions_guardian_id_idx" ON "subscriptions"("guardian_id");

-- CreateIndex
CREATE INDEX "subscriptions_athlete_id_idx" ON "subscriptions"("athlete_id");

-- CreateIndex
CREATE UNIQUE INDEX "invoices_number_key" ON "invoices"("number");

-- CreateIndex
CREATE UNIQUE INDEX "invoices_earchive_uuid_key" ON "invoices"("earchive_uuid");

-- CreateIndex
CREATE INDEX "invoices_status_due_date_idx" ON "invoices"("status", "due_date");

-- CreateIndex
CREATE INDEX "invoices_guardian_id_idx" ON "invoices"("guardian_id");

-- CreateIndex
CREATE UNIQUE INDEX "invoices_subscription_id_period_key" ON "invoices"("subscription_id", "period");

-- CreateIndex
CREATE UNIQUE INDEX "payments_receipt_no_key" ON "payments"("receipt_no");

-- CreateIndex
CREATE UNIQUE INDEX "payments_provider_ref_key" ON "payments"("provider_ref");

-- CreateIndex
CREATE INDEX "payments_paid_at_idx" ON "payments"("paid_at");

-- CreateIndex
CREATE INDEX "payments_invoice_id_idx" ON "payments"("invoice_id");

-- CreateIndex
CREATE UNIQUE INDEX "payment_reminders_invoice_id_level_key" ON "payment_reminders"("invoice_id", "level");

-- CreateIndex
CREATE UNIQUE INDEX "payrolls_timesheet_id_key" ON "payrolls"("timesheet_id");

-- CreateIndex
CREATE UNIQUE INDEX "payrolls_staff_id_period_key" ON "payrolls"("staff_id", "period");

-- CreateIndex
CREATE INDEX "expenses_spent_at_idx" ON "expenses"("spent_at");

-- CreateIndex
CREATE INDEX "expenses_category_spent_at_idx" ON "expenses"("category", "spent_at");

-- CreateIndex
CREATE UNIQUE INDEX "campaigns_channel_external_id_key" ON "campaigns"("channel", "external_id");

-- CreateIndex
CREATE UNIQUE INDEX "leads_external_lead_id_key" ON "leads"("external_lead_id");

-- CreateIndex
CREATE UNIQUE INDEX "leads_athlete_id_key" ON "leads"("athlete_id");

-- CreateIndex
CREATE INDEX "leads_stage_idx" ON "leads"("stage");

-- CreateIndex
CREATE INDEX "leads_phone_idx" ON "leads"("phone");

-- CreateIndex
CREATE INDEX "leads_campaign_id_created_at_idx" ON "leads"("campaign_id", "created_at");

-- CreateIndex
CREATE INDEX "leads_created_at_idx" ON "leads"("created_at");

-- CreateIndex
CREATE INDEX "lead_activities_lead_id_created_at_idx" ON "lead_activities"("lead_id", "created_at");

-- CreateIndex
CREATE UNIQUE INDEX "trial_bookings_lead_id_session_id_key" ON "trial_bookings"("lead_id", "session_id");

-- CreateIndex
CREATE UNIQUE INDEX "notification_outbox_dedupe_key_key" ON "notification_outbox"("dedupe_key");

-- CreateIndex
CREATE INDEX "notification_outbox_status_created_at_idx" ON "notification_outbox"("status", "created_at");

-- AddForeignKey
ALTER TABLE "users" ADD CONSTRAINT "users_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "users" ADD CONSTRAINT "users_guardian_id_fkey" FOREIGN KEY ("guardian_id") REFERENCES "guardians"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "audit_logs" ADD CONSTRAINT "audit_logs_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "shifts" ADD CONSTRAINT "shifts_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "shifts" ADD CONSTRAINT "shifts_facility_id_fkey" FOREIGN KEY ("facility_id") REFERENCES "facilities"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "time_entries" ADD CONSTRAINT "time_entries_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "time_entries" ADD CONSTRAINT "time_entries_approved_by_id_fkey" FOREIGN KEY ("approved_by_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "time_entries" ADD CONSTRAINT "time_entries_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "training_sessions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "time_entries" ADD CONSTRAINT "time_entries_timesheet_id_fkey" FOREIGN KEY ("timesheet_id") REFERENCES "timesheets"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "timesheets" ADD CONSTRAINT "timesheets_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "teams" ADD CONSTRAINT "teams_season_id_fkey" FOREIGN KEY ("season_id") REFERENCES "seasons"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "teams" ADD CONSTRAINT "teams_head_coach_id_fkey" FOREIGN KEY ("head_coach_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "teams" ADD CONSTRAINT "teams_default_fee_plan_id_fkey" FOREIGN KEY ("default_fee_plan_id") REFERENCES "fee_plans"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "team_coaches" ADD CONSTRAINT "team_coaches_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "teams"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "team_coaches" ADD CONSTRAINT "team_coaches_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "athlete_guardians" ADD CONSTRAINT "athlete_guardians_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "athlete_guardians" ADD CONSTRAINT "athlete_guardians_guardian_id_fkey" FOREIGN KEY ("guardian_id") REFERENCES "guardians"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "team_memberships" ADD CONSTRAINT "team_memberships_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "team_memberships" ADD CONSTRAINT "team_memberships_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "teams"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_plans" ADD CONSTRAINT "training_plans_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "teams"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_plans" ADD CONSTRAINT "training_plans_coach_id_fkey" FOREIGN KEY ("coach_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_plans" ADD CONSTRAINT "training_plans_facility_id_fkey" FOREIGN KEY ("facility_id") REFERENCES "facilities"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_sessions" ADD CONSTRAINT "training_sessions_plan_id_fkey" FOREIGN KEY ("plan_id") REFERENCES "training_plans"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_sessions" ADD CONSTRAINT "training_sessions_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "teams"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_sessions" ADD CONSTRAINT "training_sessions_coach_id_fkey" FOREIGN KEY ("coach_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "training_sessions" ADD CONSTRAINT "training_sessions_facility_id_fkey" FOREIGN KEY ("facility_id") REFERENCES "facilities"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session_blocks" ADD CONSTRAINT "session_blocks_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "training_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "session_blocks" ADD CONSTRAINT "session_blocks_drill_id_fkey" FOREIGN KEY ("drill_id") REFERENCES "drills"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendances" ADD CONSTRAINT "attendances_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "training_sessions"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "attendances" ADD CONSTRAINT "attendances_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "assessments" ADD CONSTRAINT "assessments_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "assessments" ADD CONSTRAINT "assessments_assessor_id_fkey" FOREIGN KEY ("assessor_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurements" ADD CONSTRAINT "measurements_assessment_id_fkey" FOREIGN KEY ("assessment_id") REFERENCES "assessments"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "measurements" ADD CONSTRAINT "measurements_metric_id_fkey" FOREIGN KEY ("metric_id") REFERENCES "metric_definitions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "games" ADD CONSTRAINT "games_team_id_fkey" FOREIGN KEY ("team_id") REFERENCES "teams"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_stats" ADD CONSTRAINT "game_stats_game_id_fkey" FOREIGN KEY ("game_id") REFERENCES "games"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "game_stats" ADD CONSTRAINT "game_stats_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "performance_reports" ADD CONSTRAINT "performance_reports_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_guardian_id_fkey" FOREIGN KEY ("guardian_id") REFERENCES "guardians"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "subscriptions" ADD CONSTRAINT "subscriptions_fee_plan_id_fkey" FOREIGN KEY ("fee_plan_id") REFERENCES "fee_plans"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_subscription_id_fkey" FOREIGN KEY ("subscription_id") REFERENCES "subscriptions"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_guardian_id_fkey" FOREIGN KEY ("guardian_id") REFERENCES "guardians"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoices" ADD CONSTRAINT "invoices_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "invoice_lines" ADD CONSTRAINT "invoice_lines_invoice_id_fkey" FOREIGN KEY ("invoice_id") REFERENCES "invoices"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payments" ADD CONSTRAINT "payments_invoice_id_fkey" FOREIGN KEY ("invoice_id") REFERENCES "invoices"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payments" ADD CONSTRAINT "payments_guardian_id_fkey" FOREIGN KEY ("guardian_id") REFERENCES "guardians"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payment_reminders" ADD CONSTRAINT "payment_reminders_invoice_id_fkey" FOREIGN KEY ("invoice_id") REFERENCES "invoices"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payrolls" ADD CONSTRAINT "payrolls_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "payrolls" ADD CONSTRAINT "payrolls_timesheet_id_fkey" FOREIGN KEY ("timesheet_id") REFERENCES "timesheets"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "expenses" ADD CONSTRAINT "expenses_campaign_id_fkey" FOREIGN KEY ("campaign_id") REFERENCES "campaigns"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ad_spend_daily" ADD CONSTRAINT "ad_spend_daily_campaign_id_fkey" FOREIGN KEY ("campaign_id") REFERENCES "campaigns"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leads" ADD CONSTRAINT "leads_campaign_id_fkey" FOREIGN KEY ("campaign_id") REFERENCES "campaigns"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leads" ADD CONSTRAINT "leads_owner_id_fkey" FOREIGN KEY ("owner_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "leads" ADD CONSTRAINT "leads_athlete_id_fkey" FOREIGN KEY ("athlete_id") REFERENCES "athletes"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "lead_activities" ADD CONSTRAINT "lead_activities_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "lead_activities" ADD CONSTRAINT "lead_activities_staff_id_fkey" FOREIGN KEY ("staff_id") REFERENCES "staff"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "trial_bookings" ADD CONSTRAINT "trial_bookings_lead_id_fkey" FOREIGN KEY ("lead_id") REFERENCES "leads"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "trial_bookings" ADD CONSTRAINT "trial_bookings_session_id_fkey" FOREIGN KEY ("session_id") REFERENCES "training_sessions"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

