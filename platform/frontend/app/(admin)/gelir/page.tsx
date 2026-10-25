import { redirect } from "next/navigation";

import { IncomeDashboard } from "@/components/income/IncomeDashboard";
import { ApiError } from "@/lib/api/errors";
import { incomePath, isSeason } from "@/lib/api/income";
import { serverFetch } from "@/lib/api/server";
import type { IncomeOverview } from "@/lib/types/income";

export const dynamic = "force-dynamic";

type Props = { searchParams: Promise<{ season?: string }> };

/** Drive gelir takibi: ilk veri sunucuda, sonrası SWR (aynı anahtar → hydration'da ikinci istek yok). */
export default async function IncomePage({ searchParams }: Props) {
  const { season } = await searchParams;
  const initialSeason = isSeason(season) ? season : null;
  const key = incomePath(initialSeason);

  let initial: IncomeOverview | undefined;
  try {
    initial = await serverFetch<IncomeOverview>(key);
  } catch (e) {
    if (e instanceof ApiError && e.isAuth) redirect("/login?next=/gelir");
    if (e instanceof ApiError && e.isForbidden) {
      return (
        <main className="mx-auto max-w-xl p-8">
          <h1 className="text-lg font-semibold">Yetkisiz</h1>
          <p className="mt-2 text-ink-2">Gelir paneli yönetim, finans ve pazarlama rolleri içindir.</p>
        </main>
      );
    }
  }

  return <IncomeDashboard initialSeason={initialSeason} fallback={initial ? { [key]: initial } : {}} />;
}
