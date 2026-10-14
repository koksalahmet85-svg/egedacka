// Sezon karşılaştırma: tahsilat defterinden (Excel) gelen veriyle iki sezon.
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { SeasonComparisonView } from "@/components/seasons/SeasonComparisonView";
import { AUTH_COOKIE, ApiError, apiFetch } from "@/lib/api";
import type { NotReturnedPlayer, SeasonComparison } from "@/lib/types";

export const dynamic = "force-dynamic";

export default async function SeasonsPage({ searchParams }: { searchParams: Promise<{ base?: string; target?: string }> }) {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) redirect("/login?next=/dashboard/sezonlar");
  const { base = "2025-2026", target = "2026-2027" } = await searchParams;
  const q = new URLSearchParams({ base, target });

  try {
    // İki istek paralel — sıralı bekleme (waterfall) yok.
    const [comparison, notReturned] = await Promise.all([
      apiFetch<SeasonComparison>(`/ledger/compare?${q}&mode=economic`, { token }),
      apiFetch<NotReturnedPlayer[]>(`/ledger/not-returned?${q}`, { token }),
    ]);
    return <SeasonComparisonView initial={comparison} notReturned={notReturned} base={base} target={target} />;
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/login?next=/dashboard/sezonlar");
    const msg = e instanceof ApiError && e.status === 404 ? e.message : "Analiz yüklenemedi.";
    return <SeasonComparisonView initial={null} notReturned={[]} base={base} target={target} error={msg} />;
  }
}
