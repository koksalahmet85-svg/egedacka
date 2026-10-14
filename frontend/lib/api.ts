// Tek veri erişim katmanı.
//
// Güvenlik: JWT httpOnly cookie'de durur, tarayıcı JS'i token'ı hiç görmez (XSS'e karşı).
//  - Sunucu bileşenleri  → FastAPI'ye doğrudan (Docker iç ağı), token cookie'den eklenir.
//  - İstemci bileşenleri → /api/backend/* (Next route handler) → FastAPI. Aynı origin, CORS yok.
import type { DateRange, ExecutiveSummary } from "./types";

export const AUTH_COOKIE = "ea_token";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

const INTERNAL_API = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

interface FetchOpts {
  signal?: AbortSignal;
  token?: string; // yalnız sunucu tarafında
  timeoutMs?: number;
}

export async function apiFetch<T>(path: string, { signal, token, timeoutMs = 10_000 }: FetchOpts = {}): Promise<T> {
  const onServer = typeof window === "undefined";
  const url = onServer ? `${INTERNAL_API}${path}` : `/api/backend${path}`;

  // Kullanıcının iptali (filtre değişti) ile zaman aşımını tek sinyalde birleştir.
  const timeout = AbortSignal.timeout(timeoutMs);
  const combined = signal ? AbortSignal.any([signal, timeout]) : timeout;

  const res = await fetch(url, {
    signal: combined,
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    cache: "no-store", // finans verisi: Next'in kalıcı fetch cache'ine girmesin (backend zaten 60 sn cache'liyor)
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* gövde JSON değil */
    }
    throw new ApiError(res.status, typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json() as Promise<T>;
}

export function executivePath(range: DateRange): string {
  const q = new URLSearchParams({ date_from: range.from, date_to: range.to });
  return `/dashboard/executive?${q}`;
}

export const getExecutiveSummary = (range: DateRange, opts?: FetchOpts) =>
  apiFetch<ExecutiveSummary>(executivePath(range), opts);

// ── Tarih aralığı ön ayarları ────────────────────────────────────────────────
const iso = (d: Date) => d.toISOString().slice(0, 10);

export type RangePreset = "mtd" | "3m" | "6m" | "ytd" | "12m";

export const PRESET_LABELS: Record<RangePreset, string> = {
  mtd: "Bu ay",
  "3m": "Son 3 ay",
  "6m": "Son 6 ay",
  ytd: "Yılbaşından beri",
  "12m": "Son 12 ay",
};

export function presetRange(p: RangePreset, today = new Date()): DateRange {
  const y = today.getFullYear();
  const m = today.getMonth();
  const startOf = (monthsBack: number) => new Date(Date.UTC(y, m - monthsBack, 1));
  const from = {
    mtd: startOf(0),
    "3m": startOf(2),
    "6m": startOf(5),
    ytd: new Date(Date.UTC(y, 0, 1)),
    "12m": startOf(11),
  }[p];
  return { from: iso(from), to: iso(today) };
}
