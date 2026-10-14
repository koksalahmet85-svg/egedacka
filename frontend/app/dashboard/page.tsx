// Sunucu bileşeni: ilk veri burada, sunucu-sunucu (Docker iç ağı) çekilir.
// Tarayıcı ilk boyamada dolu HTML alır → spinner yok, istemci→API→DB şelalesi yok.
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import { ExecutiveDashboard } from "@/components/dashboard/ExecutiveDashboard";
import { AUTH_COOKIE, ApiError, getExecutiveSummary, presetRange } from "@/lib/api";
import type { ExecutiveSummary } from "@/lib/types";

export const dynamic = "force-dynamic"; // kullanıcıya özel, statik üretilmez

export default async function DashboardPage() {
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) redirect("/login?next=/dashboard");

  const range = presetRange("6m");
  let initial: ExecutiveSummary | undefined;
  try {
    initial = await getExecutiveSummary(range, { token, timeoutMs: 5_000 });
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) redirect("/login?next=/dashboard");
    if (e instanceof ApiError && e.status === 403) {
      return <p className="p-8">Bu paneli görüntüleme yetkiniz yok.</p>;
    }
    // API geçici olarak yoksa sayfa yine açılır; istemci hook'u tekrar dener.
    initial = undefined;
  }
  return <ExecutiveDashboard initialRange={range} initialData={initial} />;
}
