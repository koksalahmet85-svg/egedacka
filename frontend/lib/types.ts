// FastAPI /api/v1/dashboard/executive yanıtının birebir tipi.
// Backend: backend/app/services/dashboard.py → executive_summary()

export interface OverdueBucket {
  bucket: "1-7" | "8-30" | "31-60" | "60+";
  count: number;
  amount: number;
}

export interface MonthlyCashflow {
  month: string; // "2026-09"
  income: number;
  expenses: number;
  payroll: number;
  net: number;
}

export interface MarketingKpis {
  spend: number;
  leads: number;
  trials: number;
  won: number;
  cpl: number | null;
  cost_per_trial: number | null;
  cac: number | null;
  lead_to_trial: number | null;
  trial_to_won: number | null;
  lead_to_won: number | null;
  realized_revenue: number;
  roas: number | null;
  ltv: number | null;
  ltv_cac: number | null;
  projected_roi: number | null;
}

export interface CampaignRow extends MarketingKpis {
  id: number | null;
  name: string;
  channel: string;
  clicks: number;
  impressions: number;
  ctr: number | null;
}

export type FunnelStage = "LEAD" | "CONTACTED" | "TRIAL_BOOKED" | "TRIAL_ATTENDED" | "WON";

export interface ExecutiveSummary {
  range: { from: string; to: string };
  finance: {
    collected: number;
    invoiced: number;
    collection_rate: number | null;
    expenses: number;
    payroll: number;
    net_cashflow: number;
    margin: number | null;
    mrr: number;
    active_athletes: number;
    arpa: number | null;
    overdue: { total: number; count: number; buckets: OverdueBucket[] };
    monthly: MonthlyCashflow[];
  };
  marketing: MarketingKpis & {
    lifetime_months: number;
    funnel: { stage: FunnelStage; count: number }[];
    median_minutes_to_contact: number | null;
    uncontacted_24h: number;
    campaigns: CampaignRow[];
  };
  alerts: {
    health_reports_expiring: number;
    invoices_over_30d: number;
    sessions_missing_attendance: number;
    failed_notifications: number;
  };
}

export interface DateRange {
  from: string; // YYYY-MM-DD
  to: string;
}

// ── Tahsilat defteri sezon karşılaştırması (/api/v1/ledger/compare) ──────────
export interface Delta {
  base: number;
  target: number;
  growth: number | null;
}

export interface SeasonSummary {
  name: string;
  total: number;
  dues: number;
  textile: number;
  event: number;
  rows: number;
  payers: number;
  season_plan: { payers: number; amount: number; share_of_dues: number | null; upfront_payers: number; upfront_amount: number };
  by_group: Record<string, { amount: number; dues: number; payers: number }>;
  by_channel: Record<string, { amount: number; share: number | null }>;
  by_month: { month: string; amount: number; dues: number; rows: number; payers: number }[];
  timeliness: Timeliness;
}

export interface Timeliness {
  n: number;
  advance: number | null;
  by_10th: number | null;
  late_same_month: number | null;
  after_month_end: number | null;
  median_days_after_month_start_when_late: number | null;
}

export interface SeasonComparison {
  mode: "economic" | "cash";
  base: SeasonSummary;
  target: SeasonSummary;
  aligned: {
    window: { months: string[]; last_month_cutoff_day: number; season_only_months?: string[] };
    total: Delta;
    dues: Delta;
    textile: Delta;
    event: Delta;
    payers: Delta;
    season_plan_amount: Delta;
    season_plan_payers: Delta;
    by_group: Record<string, Delta & { payers_base: number; payers_target: number }>;
    by_month: { base: SeasonSummary["by_month"]; target: SeasonSummary["by_month"] };
    timeliness: { base: Timeliness; target: Timeliness };
  };
  retention: {
    base_payers: number;
    base_recent_payers: number;
    recent_retained: number;
    recent_retention_rate: number | null;
    target_payers: number;
    target_new: number;
    recent_not_yet_returned: number;
  };
  price_changes: { group: string; month: string; base_price: number; target_price: number; change: number | null }[];
  season_plan_value: { base: SeasonPlanValue[]; target: SeasonPlanValue[] };
  plan_tiers: { base: PlanTierGroup[]; target: PlanTierGroup[] };
}

export interface PlanTierGroup {
  group: string;
  monthly_path: number;
  projected_months: number;
  tiers: {
    tier: "EARLY" | "STANDARD" | "LATE";
    label: string;
    price: number;
    valid_until: string | null;
    players: number;
    upfront: number;
    installment: number;
    first_paid: string | null;
    last_paid: string | null;
    after_deadline: number | null;
    discount_vs_monthly: number | null;
    breakeven_hike: number | null;
  }[];
  in_progress_players: number;
  in_progress_amount: number;
  other_price_players: number;
  other_price_amount: number;
  other_price_points: { price: number; n: number }[];
}

export interface SeasonPlanValue {
  group: string;
  monthly_path: number; // aynı 12 ayı aylık ödemenin toplamı
  projected_months: number; // henüz yaşanmamış, son fiyatla doldurulan ay sayısı
  price_points: { price: number; n: number; share: number; discount_vs_monthly: number | null; breakeven_hike: number | null }[];
}

export interface NotReturnedPlayer {
  player_key: string;
  player_name: string;
  group: string;
  last_paid_on: string;
  last3_amount: number;
}
