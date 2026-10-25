"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import useSWR, { SWRConfig } from "swr";

import { KpiTile } from "@/components/dashboard/KpiTile";
import { ApiError } from "@/lib/api/errors";
import { fetchIncome, incomePath, triggerSync } from "@/lib/api/income";
import { fmtDateTime, fmtMonthLong, fmtNum, fmtTL } from "@/lib/format";
import type { IncomeOverview } from "@/lib/types/income";

import { BilancoTable } from "./BilancoTable";
import { ChangesFeed } from "./ChangesFeed";
import { IssuesPanel } from "./IssuesPanel";
import { MonthlyIncomeChart } from "./MonthlyIncomeChart";
import { TeamTable } from "./TeamTable";
import { UnpaidTable } from "./UnpaidTable";

type Props = { initialSeason: string | null; fallback: Record<string, IncomeOverview> };

export function IncomeDashboard({ initialSeason, fallback }: Props) {
  return (
    <SWRConfig
      value={{
        fallback,
        fetcher: fetchIncome,
        onErrorRetry: (err, _k, _c, revalidate, { retryCount }) => {
          if (err instanceof ApiError && (err.isAuth || err.isForbidden)) return;
          if (retryCount >= 3) return;
          setTimeout(() => revalidate({ retryCount }), 2 ** retryCount * 1000);
        },
      }}
    >
      <Income initialSeason={initialSeason} />
    </SWRConfig>
  );
}

function Income({ initialSeason }: { initialSeason: string | null }) {
  const router = useRouter();
  const [season, setSeason] = useState<string | null>(initialSeason);
  const [syncMsg, setSyncMsg] = useState<string | null>(null);
  const [syncing, setSyncing] = useState(false);

  const { data, error, isValidating, mutate } = useSWR<IncomeOverview, ApiError>(incomePath(season), {
    keepPreviousData: true,
    refreshInterval: 5 * 60_000, // worker 15 dk'da bir Drive'ı okuyor; 5 dk yeterli
    revalidateOnFocus: true,
  });

  useEffect(() => {
    if (error?.isAuth) router.replace("/login?next=/gelir");
  }, [error, router]);

  function selectSeason(s: string) {
    setSeason(s);
    window.history.replaceState(null, "", `?season=${s}`);
  }

  async function syncNow() {
    setSyncing(true);
    setSyncMsg(null);
    try {
      const r = await triggerSync();
      setSyncMsg(r.status === "skipped" ? (r.reason ?? "Atlandı") : `${r.rows} satır okundu · ${r.changes} değişiklik`);
      await mutate();
    } catch (e) {
      setSyncMsg(e instanceof ApiError ? e.message : "Senkron başarısız");
    } finally {
      setSyncing(false);
    }
  }

  if (!data) {
    return (
      <main className="mx-auto max-w-7xl p-6">
        {error ? (
          <div role="alert">
            <p className="font-medium">Veriler alınamadı: {error.message}</p>
            <button onClick={() => mutate()} className="mt-3 rounded-md bg-brand px-3 py-2 text-white">Tekrar dene</button>
          </div>
        ) : (
          <p className="text-ink-2">Yükleniyor…</p>
        )}
      </main>
    );
  }

  const sync = data.lastSync;
  const header = (
    <header className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-2xl font-semibold">Gelir Takibi</h1>
        <p className="text-sm text-ink-2">
          Kaynak: Drive · Genel Ödeme Tablosu
          {sync && (
            <>
              {" · "}son okuma {fmtDateTime(sync.at)}
              {sync.status === "FAILED" && <span className="text-critical"> ▼ başarısız: {sync.error}</span>}
            </>
          )}
          {isValidating && <span className="ml-2 text-ink-muted">yenileniyor…</span>}
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {data.seasons.length > 0 && (
          <label className="text-sm text-ink-2">
            Sezon{" "}
            <select
              value={data.season ?? ""}
              onChange={(e) => selectSeason(e.target.value)}
              className="rounded-md border border-[var(--border)] bg-surface px-2 py-1.5 text-ink"
            >
              {data.seasons.map((s) => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </label>
        )}
        <button
          onClick={syncNow}
          disabled={syncing}
          className="rounded-md bg-brand px-3 py-1.5 text-sm font-semibold text-white disabled:opacity-60"
        >
          {syncing ? "Drive okunuyor…" : "Drive'dan şimdi oku"}
        </button>
        {syncMsg && <span className="text-xs text-ink-2" role="status">{syncMsg}</span>}
      </div>
    </header>
  );

  if (data.empty || !data.kpis || !data.months || !data.programs) {
    return (
      <main className="mx-auto max-w-3xl space-y-6 px-4 py-6">
        {header}
        <section className="rounded-xl border border-[var(--border)] bg-surface p-5 text-sm leading-6">
          <h2 className="mb-2 font-semibold">Henüz Drive verisi yok</h2>
          <ol className="list-decimal space-y-1 pl-5 text-ink-2">
            <li>Sunucudaki <code>.env</code> dosyasında <code>DRIVE_INCOME_SPREADSHEET_ID</code> ve <code>GOOGLE_SERVICE_ACCOUNT_JSON</code> tanımlı olmalı.</li>
            <li>Ödeme tablosunu servis hesabının e-postasıyla <strong>Görüntüleyen</strong> olarak paylaşın.</li>
            <li>&quot;Drive&apos;dan şimdi oku&quot; ile ilk okumayı başlatın; sonrası her 15 dakikada otomatik.</li>
          </ol>
        </section>
      </main>
    );
  }

  const k = data.kpis;
  const c = data.counts!;
  const cur = data.currentMonth!;
  const delta = k.prevMonthTotal ? ((k.monthTotal - k.prevMonthTotal) / k.prevMonthTotal) * 100 : null;

  return (
    <main className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6">
      {header}

      <section aria-label="Özet" className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <KpiTile label={`Sezon toplamı (${data.season})`} value={fmtTL(k.seasonTotal)}
          hint={`Tekstil ayrıca ${fmtTL(k.textileTotal)}`} />
        <KpiTile label={`${fmtMonthLong(cur)} gelir`} value={fmtTL(k.monthTotal)}
          hint={delta == null ? "Önceki ay verisi yok" : `Önceki ay ${fmtTL(k.prevMonthTotal)}`} />
        <KpiTile label="Bu ay ödeyen / ödemeyen" value={`${fmtNum(k.monthPayers)} / ${fmtNum(k.monthNonPayers)}`}
          tone={k.monthNonPayers > 0 ? "warning" : "good"} hint="Aylık ödeyenlerde boş hücre" />
        <KpiTile label="Gecikmiş (geçmiş ay)" value={`${fmtNum(k.overdueAthletes)} sporcu`}
          tone={k.overdueAthletes > 0 ? "critical" : "good"} hint={`Tahmini açık ${fmtTL(k.estimatedOpen)}`} />
        <KpiTile label="Sezonluk taksit bekleyen" value={fmtNum(k.pendingInstallments)}
          tone={k.pendingInstallments > 0 ? "warning" : undefined} hint="Geçmiş ayda boş taksit hücresi" />
        <KpiTile label="Aktif sporcu" value={fmtNum(c.active)}
          hint={`${c.monthly} aylık · ${c.seasonal} sezonluk · ${c.scholarship + c.partialScholarship} burslu`} />
      </section>

      <div className="grid gap-4 xl:grid-cols-5">
        <MonthlyIncomeChart className="xl:col-span-3" months={data.months} programs={data.programs} />
        <ChangesFeed className="xl:col-span-2" changes={data.recentChanges ?? []} />
      </div>

      <BilancoTable months={data.months} programs={data.programs} currentMonth={cur} />
      <UnpaidTable rows={data.unpaid ?? []} currentMonth={cur} programs={data.programs} />
      <TeamTable rows={data.teams ?? []} programs={data.programs} />
      <IssuesPanel issues={data.issues ?? []} total={data.issueCount ?? 0} sources={data.sources ?? []} />

      <p className="text-xs text-ink-muted">
        Aylar tablodaki aidat sütunlarıdır (ödemenin ait olduğu ay). &quot;Ekim&apos;de Eylül aidatını ödedi&quot; gibi
        durumlarda tutar Eylül sütunundaysa Eylül&apos;e yazılır. Bırakan (not: BIRAKTI), aday (DENEME, ARANACAK) ve burslu
        sporcular ödemeyen sayılmaz.
      </p>
    </main>
  );
}
