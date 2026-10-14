"use client";

import { useMemo, useState } from "react";

import type { CampaignRow } from "@/lib/types";

import { fmt } from "./format";

type SortKey = "spend" | "leads" | "won" | "cac" | "roas" | "projected_roi";

const COLS: { key: SortKey; label: string; render: (c: CampaignRow) => string; title: string }[] = [
  { key: "spend", label: "Harcama", render: (c) => fmt.tl(c.spend), title: "Reklam + kampanyaya bağlı giderler" },
  { key: "leads", label: "Lead", render: (c) => fmt.n(c.leads), title: "Dönemde oluşan lead (kohort)" },
  { key: "won", label: "Kayıt", render: (c) => fmt.n(c.won), title: "Kohorttan bugüne kadar kayıt olan" },
  { key: "cac", label: "CAC", render: (c) => fmt.tl(c.cac), title: "Harcama / kayıt" },
  { key: "roas", label: "ROAS", render: (c) => fmt.x(c.roas), title: "Kayıt sonrası tahsil edilen / harcama" },
  { key: "projected_roi", label: "Öng. ROI", render: (c) => fmt.x(c.projected_roi),
    title: "(kayıt × LTV − harcama) / harcama" },
];

export function CampaignTable({ rows }: { rows: CampaignRow[] }) {
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: "projected_roi", desc: true });
  const sorted = useMemo(() => {
    const v = (c: CampaignRow) => c[sort.key] ?? -Infinity;
    return [...rows].sort((a, b) => (sort.desc ? v(b) - v(a) : v(a) - v(b)));
  }, [rows, sort]);

  return (
    <section className="overflow-x-auto rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">Kampanya performansı</h2>
      <table className="tabular w-full min-w-[640px] text-sm">
        <thead>
          <tr className="text-left text-ink-2">
            <th className="py-1">Kampanya</th>
            <th className="pl-3">Huni<span className="block text-xs font-normal text-muted">lead→deneme · deneme→kayıt</span></th>
            {COLS.map((c) => (
              <th key={c.key} className="pl-3 text-right whitespace-nowrap" title={c.title}>
                <button onClick={() => setSort((s) => ({ key: c.key, desc: s.key === c.key ? !s.desc : true }))}>
                  {c.label}{sort.key === c.key ? (sort.desc ? " ↓" : " ↑") : ""}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {sorted.map((c) => (
            <tr key={c.id ?? "organic"} className="border-t border-line">
              <td className="py-1.5">
                <div className="font-medium">{c.name}</div>
                <div className="text-xs text-muted">{c.channel}</div>
              </td>
              <td className="pl-3 text-xs whitespace-nowrap text-ink-2">
                {fmt.pct(c.lead_to_trial)} · {fmt.pct(c.trial_to_won)}
              </td>
              {COLS.map((col) => (
                <td key={col.key} className="pl-3 text-right whitespace-nowrap">{col.render(c)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
