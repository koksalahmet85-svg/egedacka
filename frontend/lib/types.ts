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
