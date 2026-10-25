import type { IncomeOverview } from "@/lib/types/income";

import { clientFetch, clientPost } from "./client";

export function incomePath(season?: string | null): string {
  return season ? `/income/overview?season=${encodeURIComponent(season)}` : "/income/overview";
}

export const fetchIncome = (path: string) => clientFetch<IncomeOverview>(path);

export type SyncResult = {
  status: "ok" | "skipped";
  sheets?: string[];
  skippedSheets?: string[];
  rows?: number;
  changes?: number;
  reason?: string;
};

export const triggerSync = () => clientPost<SyncResult>("/income/sync");

export const isSeason = (v: string | undefined): v is string => !!v && /^\d{4}-\d{2}$/.test(v);
