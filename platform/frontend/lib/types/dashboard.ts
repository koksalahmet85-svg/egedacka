// Backend sözleşmesi: backend/app/schemas/dashboard.py ile birebir aynı tutulur.

export interface OverdueBlock {
  amount: number;
  count: number;
  families: number;
  over30DaysAmount: number;
}

export interface SeriesPoint {
  month: string; // "2026-10"
  income: number;
  opex: number;
  ad_spend: number;
  net: number;
  leads: number;
  won: number;
}

export interface FinanceBlock {
  revenue: number;
  operatingExpenses: number;
  adSpend: number;
  totalExpenses: number;
  net: number;
  marginPct: number | null;
  billed: number;
  collectionRatePct: number | null;
  overdue: OverdueBlock;
  mrr: number;
  activeAthletes: number;
  avgMonthlyFee: number;
  monthlyChurnPct: number;
  series: SeriesPoint[];
}

export interface FunnelBlock {
  leads: number;
  contacted: number;
  trialScheduled: number;
  trialAttended: number;
  won: number;
  contactRate: number | null;
  trialBookRate: number | null;
  trialShowRate: number | null;
  trialToMemberRate: number | null;
  leadToMemberRate: number | null;
}

export interface PaidBlock {
  leads: number;
  won: number;
  attributedRevenue: number;
  spend: number;
  cpl: number | null;
  cac: number | null;
  roas: number | null;
  roi: number | null;
  ltv: number;
  ltvToCac: number | null;
  paybackMonths: number | null;
}

export interface ChannelRow {
  channel: string;
  leads: number;
  contacted: number;
  trialScheduled: number;
  trialAttended: number;
  won: number;
  lost: number;
  leadToMemberPct: number | null;
  medianResponseMin: number | null;
}

export interface CampaignRow {
  id: string;
  name: string;
  platform: string;
  spend: number;
  impressions: number;
  clicks: number;
  ctrPct: number | null;
  leads: number;
  trials: number;
  won: number;
  revenue: number;
  cpl: number | null;
  cac: number | null;
  roas: number | null;
  roi: number | null;
  ltvToCac: number | null;
}

export interface DashboardOverview {
  range: { from: string; to: string };
  generatedAt: string;
  finance: FinanceBlock;
  marketing: {
    funnel: FunnelBlock;
    paid: PaidBlock;
    expectedTenureMonths: number;
    channels: ChannelRow[];
    campaigns: CampaignRow[];
  };
  combined: {
    adSpendShareOfRevenuePct: number | null;
    newMrrFromMarketing: number;
    marketingPaybackMonths: number | null;
  };
}

/** Yarı açık aralık: from dahil, to hariç (YYYY-MM-DD). */
export interface DateRange {
  from: string;
  to: string;
}
