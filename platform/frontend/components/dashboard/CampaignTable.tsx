import { fmtNum, fmtPct, fmtTL, fmtX } from "@/lib/format";
import type { CampaignRow } from "@/lib/types/dashboard";

function Roi({ v }: { v: number | null }) {
  if (v == null) return <>—</>;
  const up = v >= 0;
  return (
    <span className={up ? "text-good" : "text-critical"}>
      <span aria-hidden>{up ? "▲" : "▼"}</span> {fmtPct(v)}
    </span>
  );
}

export function CampaignTable({ rows }: { rows: CampaignRow[] }) {
  return (
    <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-surface p-4">
      <h3 className="mb-3 font-semibold">Kampanya performansı</h3>
      {rows.length === 0 ? (
        <p className="text-sm text-ink-2">Bu dönemde kampanya verisi yok.</p>
      ) : (
        <table className="tabular w-full min-w-[860px] text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              <th className="py-2 font-medium">Kampanya</th>
              <th className="py-2 text-right font-medium">Harcama</th>
              <th className="py-2 text-right font-medium">TO</th>
              <th className="py-2 text-right font-medium">Lead</th>
              <th className="py-2 text-right font-medium">Deneme</th>
              <th className="py-2 text-right font-medium">Üye</th>
              <th className="py-2 text-right font-medium">CPL</th>
              <th className="py-2 text-right font-medium">CAC</th>
              <th className="py-2 text-right font-medium">Tahsilat</th>
              <th className="py-2 text-right font-medium">ROAS</th>
              <th className="py-2 text-right font-medium">ROI</th>
              <th className="py-2 text-right font-medium">LTV:CAC</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="py-2">
                  <span className="font-medium">{r.name}</span>
                  <span className="ml-2 rounded bg-line px-1.5 py-0.5 text-[10px] text-ink-2">{r.platform}</span>
                </td>
                <td className="py-2 text-right">{fmtTL(r.spend)}</td>
                <td className="py-2 text-right" title="Tıklama oranı">{fmtPct(r.ctrPct)}</td>
                <td className="py-2 text-right">{fmtNum(r.leads)}</td>
                <td className="py-2 text-right">{fmtNum(r.trials)}</td>
                <td className="py-2 text-right">{fmtNum(r.won)}</td>
                <td className="py-2 text-right">{fmtTL(r.cpl)}</td>
                <td className="py-2 text-right">{fmtTL(r.cac)}</td>
                <td className="py-2 text-right">{fmtTL(r.revenue)}</td>
                <td className="py-2 text-right">{fmtX(r.roas)}</td>
                <td className="py-2 text-right"><Roi v={r.roi} /></td>
                <td className="py-2 text-right">{fmtX(r.ltvToCac)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
