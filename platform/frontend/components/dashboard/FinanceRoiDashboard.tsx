"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import useSWR, { preload, SWRConfig } from "swr";

import { fetchOverview, overviewPath, presetRange, RANGE_PRESETS, type RangePreset } from "@/lib/api/dashboard";
import { ApiError } from "@/lib/api/errors";
import { fmtNum, fmtPct, fmtTL, fmtX } from "@/lib/format";
import type { DashboardOverview } from "@/lib/types/dashboard";

import { CampaignTable } from "./CampaignTable";
import { CashflowChart } from "./CashflowChart";
import { ChannelTable } from "./ChannelTable";
import { FunnelChart } from "./FunnelChart";
import { KpiTile } from "./KpiTile";

type Props = {
  initialPreset: RangePreset;
  fallback: Record<string, DashboardOverview>;
};

export function FinanceRoiDashboard({ initialPreset, fallback }: Props) {
  return (
    <SWRConfig
      value={{
        fallback,
        fetcher: fetchOverview,
        // Yetki hatalarında tekrar deneme anlamsız; diğerlerinde üstel geri çekilme (en fazla 3).
        onErrorRetry: (err, _key, _cfg, revalidate, { retryCount }) => {
          if (err instanceof ApiError && (err.isAuth || err.isForbidden)) return;
          if (retryCount >= 3) return;
          setTimeout(() => revalidate({ retryCount }), 2 ** retryCount * 1000);
        },
      }}
    >
      <Dashboard initialPreset={initialPreset} />
    </SWRConfig>
  );
}

function Dashboard({ initialPreset }: { initialPreset: RangePreset }) {
  const router = useRouter();
  const [preset, setPreset] = useState<RangePreset>(initialPreset);
  const key = useMemo(() => overviewPath(presetRange(preset)), [preset]);

  const { data, error, isValidating, mutate } = useSWR<DashboardOverview, ApiError>(key, {
    keepPreviousData: true, // aralık değişirken eski veri ekranda kalır, boş ekran yanıp sönmez
    refreshInterval: 60_000, // backend önbelleği 60 sn; daha sık sorgu israf
    revalidateOnFocus: true,
    dedupingInterval: 30_000,
  });

  useEffect(() => {
    if (error?.isAuth) router.replace("/login?next=/dashboard");
  }, [error, router]);

  function selectPreset(p: RangePreset) {
    setPreset(p);
    // URL paylaşılabilir kalsın ama sunucu yeniden render edilmesin (SWR zaten çekiyor).
    window.history.replaceState(null, "", `?range=${p}`);
  }

  // Kullanıcı butonun üstüne geldiğinde veriyi önceden ısıt → tıklamada anlık geçiş.
  const warm = (p: RangePreset) => void preload(overviewPath(presetRange(p)), fetchOverview);

  if (!data) {
    return (
      <main className="mx-auto max-w-7xl p-6">
        {error ? (
          <div role="alert">
            <p className="font-medium">Veriler alınamadı: {error.message}</p>
            <button onClick={() => mutate()} className="mt-3 rounded-md bg-brand px-3 py-2 text-white">
              Tekrar dene
            </button>
          </div>
        ) : (
          <p className="text-ink-2">Yükleniyor…</p>
        )}
      </main>
    );
  }

  const { finance: f, marketing: m, combined: c } = data;
  const updated = new Date(data.generatedAt).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" });

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Finans & Pazarlama ROI</h1>
          <p className="text-sm text-ink-2">
            {data.range.from} → {data.range.to} (hariç) · güncellendi {updated}
            {isValidating && <span className="ml-2 text-ink-muted">yenileniyor…</span>}
            {error && data && <span className="ml-2 text-critical">· son yenileme başarısız, eski veri gösteriliyor</span>}
          </p>
        </div>
        <nav aria-label="Tarih aralığı" className="flex flex-wrap gap-1 rounded-lg border border-[var(--border)] bg-surface p-1">
          {RANGE_PRESETS.map((p) => (
            <button
              key={p.key}
              onClick={() => selectPreset(p.key)}
              onMouseEnter={() => warm(p.key)}
              onFocus={() => warm(p.key)}
              aria-pressed={preset === p.key}
              className={`rounded-md px-3 py-1.5 text-sm ${preset === p.key ? "bg-brand font-semibold text-white" : "text-ink-2 hover:bg-line"}`}
            >
              {p.label}
            </button>
          ))}
        </nav>
      </header>

      <section aria-labelledby="fin-h">
        <h2 id="fin-h" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">Finans</h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <KpiTile label="Tahsilat" value={fmtTL(f.revenue)} hint={`Tahakkuk ${fmtTL(f.billed)}`} />
          <KpiTile label="Net (gelir − gider)" value={fmtTL(f.net)} tone={f.net >= 0 ? "good" : "critical"}
            hint={`Marj ${fmtPct(f.marginPct)}`} />
          <KpiTile label="Tahsilat oranı" value={fmtPct(f.collectionRatePct)}
            tone={(f.collectionRatePct ?? 0) >= 92 ? "good" : "warning"} hint="Vadesi dönemde olanlar" />
          <KpiTile label="Gecikmiş alacak" value={fmtTL(f.overdue.amount)} tone={f.overdue.amount > 0 ? "critical" : "good"}
            hint={`${fmtNum(f.overdue.families)} aile · 30+ gün ${fmtTL(f.overdue.over30DaysAmount)}`} />
          <KpiTile label="Aylık tekrarlayan gelir" value={fmtTL(f.mrr)} hint={`Ort. aidat ${fmtTL(f.avgMonthlyFee)}`} />
          <KpiTile label="Aktif sporcu" value={fmtNum(f.activeAthletes)} hint={`Aylık churn ${fmtPct(f.monthlyChurnPct, 2)}`} />
        </div>
      </section>

      <section aria-labelledby="roi-h">
        <h2 id="roi-h" className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink-muted">
          Ücretli pazarlama ROI
        </h2>
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
          <KpiTile label="Reklam harcaması" value={fmtTL(m.paid.spend)}
            hint={`Gelirin ${fmtPct(c.adSpendShareOfRevenuePct)}'i`} />
          <KpiTile label="Lead başı maliyet" value={fmtTL(m.paid.cpl)} hint={`${fmtNum(m.paid.leads)} lead`} />
          <KpiTile label="Üye edinme maliyeti" value={fmtTL(m.paid.cac)} hint={`${fmtNum(m.paid.won)} yeni üye`} />
          <KpiTile label="ROI (tahsil edilen)" value={fmtPct(m.paid.roi)}
            tone={m.paid.roi == null ? undefined : m.paid.roi >= 0 ? "good" : "critical"}
            hint={`ROAS ${fmtX(m.paid.roas)}`} />
          <KpiTile label="LTV : CAC" value={fmtX(m.paid.ltvToCac)}
            tone={m.paid.ltvToCac == null ? undefined : m.paid.ltvToCac >= 3 ? "good" : "warning"}
            hint={`LTV ${fmtTL(m.paid.ltv)} (${m.expectedTenureMonths} ay)`} />
          <KpiTile label="Geri ödeme süresi" value={m.paid.paybackMonths == null ? "—" : `${m.paid.paybackMonths} ay`}
            hint={`Pazarlamadan yeni MRR ${fmtTL(c.newMrrFromMarketing)}`} />
        </div>
      </section>

      <div className="grid gap-4 lg:grid-cols-5">
        <CashflowChart className="lg:col-span-3" series={f.series} />
        <FunnelChart className="lg:col-span-2" funnel={m.funnel} />
      </div>

      <CampaignTable rows={m.campaigns} />
      <ChannelTable rows={m.channels} />

      <p className="text-xs text-ink-muted">
        ROI kohort bazlıdır: dönemde gelen lead&apos;lerden kazanılan üyelerin bugüne kadar tahsil edilen aidatları ÷ dönem
        harcaması. Yeni kampanyalarda gelir birikmediği için ROI düşük, LTV:CAC ise ileriye dönük göstergedir.
      </p>
    </main>
  );
}
