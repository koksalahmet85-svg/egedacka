import { redirect } from "next/navigation";

import { FinanceRoiDashboard } from "@/components/dashboard/FinanceRoiDashboard";
import { isPreset, overviewPath, presetRange } from "@/lib/api/dashboard";
import { ApiError } from "@/lib/api/errors";
import { serverFetch } from "@/lib/api/server";
import type { DashboardOverview } from "@/lib/types/dashboard";

// Kullanıcıya özel, her istekte taze: statik üretim ve paylaşımlı önbellek yok.
export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ range?: string }> };

/**
 * Veri akışı:
 *  1. Sunucu (RSC) seçili aralığın verisini FastAPI'den çeker → ilk boyamada veri hazır, yükleme iskeleti yok.
 *  2. Veri SWR `fallback`'ine aynı anahtarla verilir → hydration sonrası istemci tekrar istek atmaz.
 *  3. İstemci; aralık değişimi, 60 sn arka plan yenileme ve sekmeye dönüşte BFF proxy üzerinden günceller.
 */
export default async function DashboardPage({ searchParams }: Props) {
  const { range: rangeParam } = await searchParams;
  const preset = isPreset(rangeParam) ? rangeParam : "6m";
  const range = presetRange(preset);
  const key = overviewPath(range);

  let initial: DashboardOverview | undefined;
  try {
    initial = await serverFetch<DashboardOverview>(key);
  } catch (e) {
    if (e instanceof ApiError && e.isAuth) redirect("/login?next=/dashboard");
    if (e instanceof ApiError && e.isForbidden) {
      return (
        <main className="mx-auto max-w-xl p-8">
          <h1 className="text-lg font-semibold">Yetkisiz</h1>
          <p className="mt-2 text-ink-2">Bu panel yönetim, finans ve pazarlama rolleri içindir.</p>
        </main>
      );
    }
    // Geçici hata: sayfa yine render edilir, istemci SWR yeniden dener.
    initial = undefined;
  }

  return <FinanceRoiDashboard initialPreset={preset} fallback={initial ? { [key]: initial } : {}} />;
}
