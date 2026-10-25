"use client";

import { useMemo, useState } from "react";

import { fmtMonth, fmtTL } from "@/lib/format";
import type { ProgramKey, UnpaidRow } from "@/lib/types/income";

type Tab = "overdue" | "month" | "installment";
type Props = { rows: UnpaidRow[]; currentMonth: string; programs: { key: ProgramKey; label: string }[] };

export function UnpaidTable({ rows, currentMonth, programs }: Props) {
  const [tab, setTab] = useState<Tab>("overdue");
  const [program, setProgram] = useState<ProgramKey | "ALL">("ALL");
  const label = Object.fromEntries(programs.map((p) => [p.key, p.label]));

  const groups = useMemo(
    () => ({
      overdue: rows.filter((r) => r.kind === "DUE" && r.overdueMonths > 0),
      month: rows.filter((r) => r.kind === "DUE" && r.overdueMonths === 0 && r.months.includes(currentMonth)),
      installment: rows.filter((r) => r.kind === "PENDING_INSTALLMENT"),
    }),
    [rows, currentMonth],
  );
  const shown = groups[tab].filter((r) => program === "ALL" || r.program === program);

  const tabs: { key: Tab; label: string }[] = [
    { key: "overdue", label: `Gecikmiş (${groups.overdue.length})` },
    { key: "month", label: `Yalnız bu ay (${groups.month.length})` },
    { key: "installment", label: `Sezonluk taksit (${groups.installment.length})` },
  ];

  return (
    <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-surface p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Ödeme takibi</h2>
        <div className="flex flex-wrap gap-2">
          <div role="tablist" className="flex gap-1 rounded-lg border border-[var(--border)] p-1">
            {tabs.map((t) => (
              <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setTab(t.key)}
                className={`rounded-md px-2.5 py-1 text-xs ${tab === t.key ? "bg-brand font-semibold text-white" : "text-ink-2 hover:bg-line"}`}>
                {t.label}
              </button>
            ))}
          </div>
          <select value={program} onChange={(e) => setProgram(e.target.value as ProgramKey | "ALL")}
            aria-label="Program" className="rounded-md border border-[var(--border)] bg-surface px-2 text-xs">
            <option value="ALL">Tüm programlar</option>
            {programs.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
          </select>
        </div>
      </div>
      {shown.length === 0 ? (
        <p className="text-sm text-ink-2">Bu listede kimse yok.</p>
      ) : (
        <table className="tabular w-full min-w-[900px] text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              <th className="py-2 font-medium">Sporcu</th>
              <th className="py-2 font-medium">Program / takım</th>
              <th className="py-2 font-medium">Koç</th>
              <th className="py-2 font-medium">Boş aylar</th>
              <th className="py-2 text-right font-medium">Olağan aidat</th>
              <th className="py-2 text-right font-medium">Tahmini</th>
              <th className="py-2 pl-4 font-medium">Son ödeme</th>
              <th className="py-2 font-medium">Not</th>
              <th className="py-2 font-medium">Tabloda</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((r) => (
              <tr key={`${r.sheet}-${r.rowNumber}`} className="border-t border-line align-top">
                <td className="py-2 font-medium">{r.name}</td>
                <td className="py-2">
                  {label[r.program]}
                  {r.team && r.team.toLocaleUpperCase("tr") !== label[r.program]?.toLocaleUpperCase("tr") ? ` · ${r.team}` : ""}
                </td>
                <td className="py-2">{r.coach ?? "—"}</td>
                <td className="py-2">{r.months.map(fmtMonth).join(", ")}</td>
                <td className="py-2 text-right">{fmtTL(r.typicalFee)}</td>
                <td className="py-2 text-right">{fmtTL(r.estimatedAmount)}</td>
                <td className="py-2 pl-4">{r.lastPaidMonth ? fmtMonth(r.lastPaidMonth) : "—"}</td>
                <td className="max-w-[260px] py-2 pr-2 text-xs text-ink-2">{r.note ?? ""}</td>
                <td className="py-2 text-xs text-ink-muted">{r.sheet} · satır {r.rowNumber}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
