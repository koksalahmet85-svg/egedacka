"use client";

// Finans + pazarlama ROI tek ekran. Veri: useExecutiveDashboard (tek endpoint, tek istek).
import { useState, useTransition } from "react";

import { PRESET_LABELS, presetRange, type RangePreset } from "@/lib/api";
import type { DateRange, ExecutiveSummary } from "@/lib/types";
import { useExecutiveDashboard } from "@/lib/useExecutiveDashboard";

import { CampaignTable } from "./CampaignTable";
import { CashflowChart } from "./CashflowChart";
import { fmt } from "./format";
import { FunnelChart } from "./FunnelChart";
import { KpiTile } from "./KpiTile";

interface Props {
  initialRange: DateRange;
  initialData?: ExecutiveSummary;
}

export function ExecutiveDashboard({ initialRange, initialData }: Props) {
  const [preset, setPreset] = useState<RangePreset>("6m");
  const [range, setRange] = useState(initialRange);
  const [, startTransition] = useTransition();
  const { data, error, isLoading, isValidating, refresh } = useExecutiveDashboard(range, initialData);

  const choose = (p: RangePreset) => {
    setPreset(p);
    startTransition(() => setRange(presetRange(p))); // filtre tıklaması UI'yi kilitlemez
  };

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            EGE <span className="text-brand">ALFA</span> · Yönetim Paneli
          </h1>
          <p className="text-sm text-ink-2">
            Finans ve pazarlama ROI · {data ? `${data.range.from} – ${data.range.to}` : "yükleniyor"}
            {isValidating && <span className="ml-2 text-muted">· güncelleniyor…</span>}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1" role="group" aria-label="Tarih aralığı">
          {(Object.keys(PRESET_LABELS) as RangePreset[]).map((p) => (
            <button key={p} onClick={() => choose(p)} aria-pressed={preset === p}
              className={`rounded-full border px-3 py-1 text-sm ${
                preset === p ? "border-brand bg-brand text-white" : "border-line bg-surface text-ink-2"}`}>
              {PRESET_LABELS[p]}
            </button>
          ))}
          <button onClick={() => void refresh()} className="ml-1 rounded-full border border-line px-3 py-1 text-sm"
            aria-label="Yenile">↻</button>
          <a href="/dashboard/sezonlar" className="ml-1 rounded-full border border-line px-3 py-1 text-sm text-ink-2">
            Sezon karşılaştırma
          </a>
          <form method="post" action="/api/auth/logout">
            <button className="ml-1 rounded-full border border-line px-3 py-1 text-sm text-ink-2">Çıkış</button>
          </form>
        </div>
      </header>

      {error && (
        <div role="alert" className="rounded-lg border border-critical/40 bg-surface p-3 text-sm text-critical">
          ⚠ Veri alınamadı: {error.message}. {data ? "Son başarılı veri gösteriliyor." : ""}
          <button onClick={() => void refresh()} className="ml-2 underline">Tekrar dene</button>
        </div>
      )}

      {isLoading && !data ? <Skeleton /> : data ? <Body d={data} /> : null}
    </div>
  );
}

function Body({ d }: { d: ExecutiveSummary }) {
  const f = d.finance;
  const m = d.marketing;
  const a = d.alerts;
  const alerts = [
    a.invoices_over_30d > 0 && `${fmt.n(a.invoices_over_30d)} fatura 30 günden fazla gecikmede`,
    m.uncontacted_24h > 0 && `${fmt.n(m.uncontacted_24h)} lead 24 saattir aranmadı`,
    a.health_reports_expiring > 0 && `${fmt.n(a.health_reports_expiring)} sporcunun sağlık raporu 30 gün içinde bitiyor / yok`,
    a.sessions_missing_attendance > 0 && `${fmt.n(a.sessions_missing_attendance)} seansın yoklaması girilmedi`,
    a.failed_notifications > 0 && `${fmt.n(a.failed_notifications)} bildirim gönderilemedi`,
  ].filter(Boolean) as string[];

  return (
    <>
      {alerts.length > 0 && (
        <ul className="flex flex-wrap gap-2 text-sm" aria-label="Uyarılar">
          {alerts.map((t) => (
            <li key={t} className="rounded-full border border-line bg-surface px-3 py-1">
              <span aria-hidden className="mr-1 text-critical">●</span>
              {t}
            </li>
          ))}
        </ul>
      )}

      {/* Finans */}
      <section aria-label="Finans özeti" className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <KpiTile label="Tahsilat" value={fmt.tlShort(f.collected)} hint={`Faturalanan ${fmt.tlShort(f.invoiced)}`} />
        <KpiTile label="Tahsilat oranı" value={fmt.pct(f.collection_rate)}
          tone={(f.collection_rate ?? 1) < 0.9 ? "critical" : "good"} hint="Dönemde kesilen faturalar" />
        <KpiTile label="Net nakit akışı" value={fmt.tlShort(f.net_cashflow)}
          tone={f.net_cashflow < 0 ? "critical" : "good"} hint={`Marj ${fmt.pct(f.margin)}`} />
        <KpiTile label="Aylık tekrarlayan gelir" value={fmt.tlShort(f.mrr)}
          hint={`${fmt.n(f.active_athletes)} aktif sporcu · ort. ${fmt.tl(f.arpa)}`} />
        <KpiTile label="Geciken alacak" value={fmt.tlShort(f.overdue.total)} tone={f.overdue.total > 0 ? "critical" : "default"}
          hint={`${fmt.n(f.overdue.count)} fatura`} />
        <KpiTile label="Gider + bordro" value={fmt.tlShort(f.expenses + f.payroll)}
          hint={`Bordro ${fmt.tlShort(f.payroll)}`} />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="min-w-0 lg:col-span-2"><CashflowChart data={f.monthly} /></div>
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="mb-3 font-semibold">Gecikme yaşlandırma</h2>
          <table className="tabular w-full text-sm">
            <tbody>
              {f.overdue.buckets.map((b) => (
                <tr key={b.bucket} className="border-t border-line first:border-0">
                  <td className="py-1.5">{b.bucket} gün</td>
                  <td className="text-right text-ink-2">{fmt.n(b.count)} fatura</td>
                  <td className="text-right font-medium">{fmt.tl(b.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-3 text-xs text-muted">30+ gün alacağın tahsil olasılığı hızla düşer; arama listesi: Finans → Gecikenler.</p>
        </section>
      </div>

      {/* Pazarlama */}
      <section aria-label="Pazarlama özeti" className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <KpiTile label="Reklam harcaması" value={fmt.tlShort(m.spend)} hint={`Lead başı ${fmt.tl(m.cpl)}`} />
        <KpiTile label="Yeni kayıt" value={fmt.n(m.won)} hint={`Lead→kayıt ${fmt.pct(m.lead_to_won)}`} />
        <KpiTile label="CAC" value={fmt.tl(m.cac)} hint="Kayıt başı edinme maliyeti" />
        <KpiTile label="LTV : CAC" value={fmt.x(m.ltv_cac)} tone={(m.ltv_cac ?? 0) >= 3 ? "good" : "critical"}
          hint={`LTV ${fmt.tlShort(m.ltv)} (${m.lifetime_months} ay)`} />
        <KpiTile label="Gerçekleşen ROAS" value={fmt.x(m.roas)} hint="Kayıt sonrası tahsilat / harcama" />
        <KpiTile label="İlk temas (medyan)"
          value={m.median_minutes_to_contact == null ? "—" : `${Math.round(m.median_minutes_to_contact)} dk`}
          tone={m.median_minutes_to_contact == null ? "default"
            : m.median_minutes_to_contact <= 5 ? "good" : m.median_minutes_to_contact > 60 ? "critical" : "default"}
          hint="Hedef: ≤ 5 dk" />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <FunnelChart funnel={m.funnel} />
        <div className="min-w-0 lg:col-span-2"><CampaignTable rows={m.campaigns} /></div>
      </div>
    </>
  );
}

function Skeleton() {
  return (
    <div className="grid animate-pulse grid-cols-2 gap-3 md:grid-cols-6" aria-busy>
      {Array.from({ length: 12 }, (_, i) => (
        <div key={i} className="h-24 rounded-xl border border-line bg-surface" />
      ))}
    </div>
  );
}
