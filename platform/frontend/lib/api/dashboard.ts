import type { DashboardOverview, DateRange } from "@/lib/types/dashboard";

import { clientFetch } from "./client";

/** SWR anahtarı = istek yolu. Sunucu ve istemci aynı anahtarı üretir → hydration'da çift istek olmaz. */
export function overviewPath(range: DateRange): string {
  const q = new URLSearchParams({ from: range.from, to: range.to });
  return `/dashboard/overview?${q}`;
}

export const fetchOverview = (path: string) => clientFetch<DashboardOverview>(path);

// ── Tarih aralığı yardımcıları (Europe/Istanbul takvim günü, ay başı hizalı) ──

function firstOfMonth(d: Date): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), 1));
}

function addMonths(d: Date, n: number): Date {
  return new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + n, 1));
}

const iso = (d: Date) => d.toISOString().slice(0, 10);

export type RangePreset = "3m" | "6m" | "12m" | "ytd";

export const RANGE_PRESETS: { key: RangePreset; label: string }[] = [
  { key: "3m", label: "Son 3 ay" },
  { key: "6m", label: "Son 6 ay" },
  { key: "12m", label: "Son 12 ay" },
  { key: "ytd", label: "Yılbaşından beri" },
];

/** Bu ay dahil, ay sınırlarında. "to" hariç → gelecek ayın 1'i. */
export function presetRange(preset: RangePreset, now = new Date()): DateRange {
  const to = addMonths(firstOfMonth(now), 1);
  const months = { "3m": 3, "6m": 6, "12m": 12, ytd: now.getUTCMonth() + 1 }[preset];
  return { from: iso(addMonths(to, -months)), to: iso(to) };
}

export function isPreset(v: string | undefined): v is RangePreset {
  return v === "3m" || v === "6m" || v === "12m" || v === "ytd";
}
