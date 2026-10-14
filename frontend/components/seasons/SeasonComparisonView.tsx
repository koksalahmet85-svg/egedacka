"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { fmt } from "@/components/dashboard/format";
import { KpiTile } from "@/components/dashboard/KpiTile";
import { apiFetch } from "@/lib/api";
import type { Delta, NotReturnedPlayer, SeasonComparison } from "@/lib/types";

import { LedgerUpload } from "./LedgerUpload";
import { MonthBars } from "./MonthBars";

const GROUP_TR: Record<string, string> = {
  ALTYAPI: "Altyapı", SPOR_OKULU: "Spor Okulu", KIZ_TAKIMI: "Kız Takımı", MASA_TENISI: "Masa Tenisi",
  KARMA: "Karma", BILINMIYOR: "Bilinmiyor",
};
const CHANNEL_TR: Record<string, string> = {
  POS: "POS", MAIL_ORDER: "Mail order", GARANTI: "Garanti (havale)", FINANSBANK: "Finansbank (havale)",
  ISBANKASI: "İş Bankası", CASH: "Nakit", UNKNOWN: "Belirsiz",
};

const growth = (d: Delta) => (d.growth == null ? "—" : `${d.growth >= 0 ? "+" : ""}${fmt.pct(d.growth)}`);

interface Props {
  initial: SeasonComparison | null;
  notReturned: NotReturnedPlayer[];
  base: string;
  target: string;
  error?: string;
}

export function SeasonComparisonView({ initial, notReturned, base, target, error }: Props) {
  const [mode, setMode] = useState<"economic" | "cash">("economic");
  const [data, setData] = useState(initial);
  const [loading, setLoading] = useState(false);
  const cache = useRef<Partial<Record<"economic" | "cash", SeasonComparison>>>({});
  if (initial) cache.current.economic ??= initial;

  useEffect(() => {
    setData(initial);
    cache.current = initial ? { economic: initial } : {};
  }, [initial]); // yeni defter yüklenince (router.refresh) önbelleği sıfırla

  useEffect(() => {
    const hit = cache.current[mode];
    if (hit) return setData(hit);
    const ac = new AbortController();
    setLoading(true);
    apiFetch<SeasonComparison>(`/ledger/compare?base=${base}&target=${target}&mode=${mode}`, { signal: ac.signal })
      .then((d) => { cache.current[mode] = d; setData(d); })
      .catch(() => {})
      .finally(() => !ac.signal.aborted && setLoading(false));
    return () => ac.abort();
  }, [mode, base, target]);

  return (
    <div className="mx-auto max-w-7xl space-y-4 px-4 py-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <Link href="/dashboard" className="text-sm text-ink-2">← Yönetim paneli</Link>
          <h1 className="text-2xl font-bold">Sezon karşılaştırma · {base} ↔ {target}</h1>
          <p className="text-sm text-ink-2">Kaynak: tahsilat defteri (Excel){loading && " · güncelleniyor…"}</p>
        </div>
        <LedgerUpload />
      </header>

      {error || !data ? (
        <p className="rounded-lg border border-line bg-surface p-4 text-sm">
          {error ?? "Veri yok."} Yönetici sezon tarih aralıklarını tanımladıktan sonra defteri yükleyin.
        </p>
      ) : (
        <Body d={data} mode={mode} setMode={setMode} notReturned={notReturned} />
      )}
    </div>
  );
}

function Body({ d, mode, setMode, notReturned }: {
  d: SeasonComparison; mode: "economic" | "cash"; setMode: (m: "economic" | "cash") => void; notReturned: NotReturnedPlayer[];
}) {
  const a = d.aligned;
  const w = a.window;
  const first = w.months[0];
  const last = w.months[w.months.length - 1];
  const windowLabel = first && last
    ? `${fmt.month(first)} – ${w.last_month_cutoff_day} ${fmt.month(last)}, aynı dönemin geçen yılıyla`
    : "";
  const [showList, setShowList] = useState(false);

  return (
    <>
      <section className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line bg-surface p-3 text-sm">
        <div role="group" aria-label="Hesap modu" className="flex gap-1">
          {(["economic", "cash"] as const).map((m) => (
            <button key={m} onClick={() => setMode(m)} aria-pressed={mode === m}
              className={`rounded-full border px-3 py-1 ${mode === m ? "border-brand bg-brand text-white" : "border-line text-ink-2"}`}>
              {m === "economic" ? "Sezon bazlı" : "Kasa (defter sayfası)"}
            </button>
          ))}
        </div>
        <p className="text-ink-2">
          {mode === "economic"
            ? "Temmuz'da alınan sezonluk peşin/taksit ödemeleri kapsadıkları yeni sezona (12 ay) yazılır."
            : "Her ödeme, defterde girildiği ayın sezonuna yazılır."}
          {" "}Kıyas penceresi: {windowLabel}.
        </p>
      </section>

      <section className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6" aria-label="Hizalanmış dönem">
        <KpiTile label="Toplam tahsilat" value={fmt.tlShort(a.total.target)}
          tone={(a.total.growth ?? 0) < 0 ? "critical" : "good"} hint={`${growth(a.total)} · geçen yıl ${fmt.tlShort(a.total.base)}`} />
        <KpiTile label="Aidat geliri" value={fmt.tlShort(a.dues.target)}
          tone={(a.dues.growth ?? 0) < 0 ? "critical" : "good"} hint={`${growth(a.dues)} · tekstil/etkinlik hariç`} />
        <KpiTile label="Ödeyen oyuncu" value={fmt.n(a.payers.target)}
          tone={(a.payers.growth ?? 0) < 0 ? "critical" : "good"} hint={`${growth(a.payers)} · geçen yıl ${fmt.n(a.payers.base)}`} />
        <KpiTile label="Oyuncu başı aidat" value={fmt.tl(a.payers.target ? a.dues.target / a.payers.target : null)}
          hint={`geçen yıl ${fmt.tl(a.payers.base ? a.dues.base / a.payers.base : null)}`} />
        <KpiTile label="Sezonluk plan alan" value={fmt.n(a.season_plan_payers.target)}
          tone={(a.season_plan_payers.growth ?? 0) < 0 ? "critical" : "good"}
          hint={`${growth(a.season_plan_payers)} · tutar ${growth(a.season_plan_amount)}`} />
        <KpiTile label="Geri dönen oyuncu" value={fmt.pct(d.retention.recent_retention_rate)}
          hint={`${fmt.n(d.retention.recent_retained)}/${fmt.n(d.retention.base_recent_payers)} · ${fmt.n(d.retention.target_new)} yeni`} />
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="min-w-0 rounded-xl border border-line bg-surface p-4 lg:col-span-2">
          <h2 className="mb-2 font-semibold">Aylık tahsilat (hizalanmış)</h2>
          <MonthBars base={a.by_month.base} target={a.by_month.target} baseLabel={d.base.name} targetLabel={d.target.name} />
        </section>
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="mb-2 font-semibold">Fiyat değişimi (aylık aidat, en sık tutar)</h2>
          <table className="tabular w-full text-sm">
            <thead className="text-left text-ink-2"><tr><th>Grup / ay</th><th className="text-right">Önce</th><th className="text-right">Şimdi</th><th className="text-right">Δ</th></tr></thead>
            <tbody>
              {d.price_changes.map((p) => (
                <tr key={p.group + p.month} className="border-t border-line">
                  <td className="py-1">{GROUP_TR[p.group] ?? p.group} · {fmt.month(p.month)}</td>
                  <td className="text-right">{fmt.tl(p.base_price)}</td>
                  <td className="text-right">{fmt.tl(p.target_price)}</td>
                  <td className="text-right">{p.change == null ? "—" : `+${fmt.pct(p.change)}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <PlanValue d={d} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <section className="min-w-0 overflow-x-auto rounded-xl border border-line bg-surface p-4">
          <h2 className="mb-2 font-semibold">Grup bazında (hizalanmış)</h2>
          <table className="tabular w-full text-sm">
            <thead className="text-left text-ink-2"><tr><th>Grup</th><th className="text-right">Tahsilat</th><th className="text-right">Δ</th><th className="text-right">Oyuncu</th></tr></thead>
            <tbody>
              {Object.entries(a.by_group).filter(([, v]) => v.base || v.target).map(([g, v]) => (
                <tr key={g} className="border-t border-line">
                  <td className="py-1">{GROUP_TR[g] ?? g}</td>
                  <td className="text-right">{fmt.tlShort(v.target)}</td>
                  <td className={`text-right ${(v.growth ?? 0) < 0 ? "text-critical" : ""}`}>{growth(v)}</td>
                  <td className="text-right">{v.payers_base} → {v.payers_target}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="mb-2 font-semibold">Ödeme zamanlaması</h2>
          <table className="tabular w-full text-sm">
            <thead className="text-left text-ink-2"><tr><th /><th className="text-right">{d.base.name}</th><th className="text-right">{d.target.name}</th></tr></thead>
            <tbody>
              {([["Ayın 10'una kadar", "by_10th"], ["Aynı ay, 10'undan sonra", "late_same_month"], ["Ay bittikten sonra", "after_month_end"]] as const).map(([l, k]) => (
                <tr key={k} className="border-t border-line">
                  <td className="py-1">{l}</td>
                  <td className="text-right">{fmt.pct(a.timeliness.base[k])}</td>
                  <td className="text-right">{fmt.pct(a.timeliness.target[k])}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-2 text-xs text-muted">Tek aylık aidat ödemeleri. Kayıtlı karttan ayın 1–5'i otomatik çekim bu dağılımı değiştirir.</p>
        </section>
        <section className="rounded-xl border border-line bg-surface p-4">
          <h2 className="mb-2 font-semibold">Ödeme kanalı ({d.target.name})</h2>
          <ul className="space-y-1 text-sm">
            {Object.entries(d.target.by_channel).map(([c, v]) => (
              <li key={c} className="flex justify-between"><span>{CHANNEL_TR[c] ?? c}</span><span className="tabular">{fmt.pct(v.share)}</span></li>
            ))}
          </ul>
        </section>
      </div>

      <section className="rounded-xl border border-line bg-surface p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold">Henüz dönmeyen oyuncular · {fmt.n(notReturned.length)}</h2>
          <button onClick={() => setShowList((v) => !v)} className="rounded border border-line px-2 py-0.5 text-sm">
            {showList ? "Gizle" : "Arama listesini göster"}
          </button>
        </div>
        <p className="mt-1 text-xs text-muted">{d.base.name} sezonunun son 3 ayında ödeme yapıp {d.target.name} sezonunda henüz ödeme kaydı olmayanlar (sezonluk peşin ödeyenler hariç).</p>
        {showList && (
          <div className="mt-3 max-h-96 overflow-auto">
            <table className="tabular w-full text-sm">
              <thead className="sticky top-0 bg-surface text-left text-ink-2"><tr><th>Oyuncu</th><th>Grup</th><th>Son ödeme</th><th className="text-right">Son 3 ay</th></tr></thead>
              <tbody>
                {notReturned.map((p) => (
                  <tr key={p.player_key} className="border-t border-line">
                    <td className="py-1">{p.player_name}</td><td>{GROUP_TR[p.group] ?? p.group}</td>
                    <td>{p.last_paid_on}</td><td className="text-right">{fmt.tl(p.last3_amount)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}

function PlanValue({ d }: { d: SeasonComparison }) {
  const sides = [
    { name: d.base.name, rows: d.season_plan_value.base },
    { name: d.target.name, rows: d.season_plan_value.target },
  ];
  return (
    <section className="overflow-x-auto rounded-xl border border-line bg-surface p-4">
      <h2 className="font-semibold">Sezonluk peşin ↔ 12 ay aylık ödeme</h2>
      <p className="mb-3 text-xs text-muted">
        Aylık yol, defterdeki fiili aylık aidat fiyatlarından hesaplanır. Henüz gelmemiş aylar son fiyatla
        doldurulur (sezon içi zam yok varsayımı). Peşin, ancak aylık yoldan ucuzsa veli için avantajlıdır.
      </p>
      <table className="tabular w-full min-w-[640px] text-sm">
        <thead className="text-left text-ink-2">
          <tr>
            <th>Sezon · grup</th><th className="text-right">12 ay aylık</th><th className="text-right">Peşin fiyat</th>
            <th className="text-right">Alan</th><th className="text-right">Peşin avantajı</th>
            <th className="text-right" title="Kalan aylarda aylık aidata bu oranda zam gelirse peşin ile aylık eşitlenir">Başabaş zam</th>
          </tr>
        </thead>
        <tbody>
          {sides.flatMap(({ name, rows }) => rows.flatMap((g) =>
            g.price_points.length === 0
              ? [<tr key={name + g.group} className="border-t border-line"><td className="py-1">{name} · {GROUP_TR[g.group] ?? g.group}</td>
                  <td className="text-right">{fmt.tl(g.monthly_path)}</td><td colSpan={4} className="text-right text-muted">yeterli peşin kaydı yok</td></tr>]
              : g.price_points.map((p, i) => (
                <tr key={name + g.group + p.price} className="border-t border-line">
                  <td className="py-1">{i === 0 ? `${name} · ${GROUP_TR[g.group] ?? g.group}` : ""}</td>
                  <td className="text-right">{i === 0 ? <>{fmt.tl(g.monthly_path)}{g.projected_months > 0 && <span className="text-xs text-muted"> ({g.projected_months} ay tahmin)</span>}</> : ""}</td>
                  <td className="text-right">{fmt.tl(p.price)}</td>
                  <td className="text-right">{p.n} · {fmt.pct(p.share)}</td>
                  <td className={`text-right font-medium ${(p.discount_vs_monthly ?? 0) < 0.05 ? "text-critical" : "text-good"}`}>
                    {p.discount_vs_monthly == null ? "—" : fmt.pct(p.discount_vs_monthly)}
                  </td>
                  <td className="text-right">{p.breakeven_hike == null ? "—" : fmt.pct(p.breakeven_hike)}</td>
                </tr>
              ))))}
        </tbody>
      </table>
    </section>
  );
}
