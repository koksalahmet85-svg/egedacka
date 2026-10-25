// Backend sözleşmesi: backend/app/services/drive_income.py → overview()

export type ProgramKey = "SPOR_OKULU" | "ALTYAPI" | "MASA_TENISI" | "DIGER";

export interface IncomeMonth {
  month: string; // "2026-10"
  byProgram: Partial<Record<ProgramKey, number>>;
  total: number;
  payers: number;
  nonPayers: number;
  pendingInstallments: number;
  isFuture: boolean;
}

export interface UnpaidRow {
  name: string;
  program: ProgramKey;
  sheet: string;
  rowNumber: number;
  team: string | null;
  coach: string | null;
  paymentType: string;
  kind: "DUE" | "PENDING_INSTALLMENT";
  months: string[];
  overdueMonths: number;
  typicalFee: number | null;
  estimatedAmount: number | null;
  lastPaidMonth: string | null;
  note: string | null;
}

export interface TeamRow {
  program: ProgramKey;
  team: string;
  coach: string | null;
  athletes: number;
  seasonRevenue: number;
  monthRevenue: number;
  dueThisMonth: number;
}

export interface IncomeChange {
  at: string;
  name: string;
  sheet: string | null;
  month: string;
  from: string | null;
  to: string;
  fromAmount: number | null;
  toAmount: number | null;
}

export interface SyncInfo {
  at: string;
  status: "RUNNING" | "OK" | "FAILED";
  trigger: string;
  error: string | null;
  changes: number;
}

export interface IncomeOverview {
  season: string | null;
  seasons: string[];
  today: string;
  lastSync: SyncInfo | null;
  empty: boolean;
  currentMonth?: string;
  programs?: { key: ProgramKey; label: string }[];
  sources?: { title: string; program: ProgramKey; rows: number; lastSyncedAt: string | null; issues: number }[];
  kpis?: {
    seasonTotal: number;
    monthTotal: number;
    prevMonthTotal: number;
    monthPayers: number;
    monthNonPayers: number;
    overdueAthletes: number;
    estimatedOpen: number;
    pendingInstallments: number;
    textileTotal: number;
  };
  counts?: {
    active: number;
    monthly: number;
    seasonal: number;
    scholarship: number;
    partialScholarship: number;
    prospects: number;
    left: number;
  };
  months?: IncomeMonth[];
  textileByProgram?: Partial<Record<ProgramKey, number>>;
  unpaid?: UnpaidRow[];
  teams?: TeamRow[];
  recentChanges?: IncomeChange[];
  issues?: { row: number | null; name: string | null; kind: string; detail: string; sheet: string }[];
  issueCount?: number;
}
