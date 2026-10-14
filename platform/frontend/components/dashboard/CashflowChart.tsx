"use client";

import { useState } from "react";
import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { fmtMonth, fmtTL, fmtTLCompact } from "@/lib/format";
import type { SeriesPoint } from "@/lib/types/dashboard";

const SERIES = [
  { key: "income", label: "Tahsilat", color: "var(--series-1)" },
  { key: "expense", label: "Gider (reklam dahil)", color: "var(--series-2)" },
  { key: "net", label: "Net", color: "var(--series-3)" },
] as const;

/** Tek eksen (hepsi TL). Gelir/gider çubuk, net çizgi. Tablo görünümü erişilebilirlik için. */
export function CashflowChart({ series, className = "" }: { series: SeriesPoint[]; className?: string }) {
  const [asTable, setAsTable] = useState(false);
  const rows = series.map((s) => ({
    month: fmtMonth(s.month),
    income: s.income,
    expense: s.opex + s.ad_spend,
    net: s.net,
  }));

  return (
    <figure className={`rounded-xl border border-[var(--border)] bg-surface p-4 ${className}`}>
      <figcaption className="mb-3 flex items-center justify-between">
        <span className="font-semibold">Aylık nakit akışı</span>
        <button onClick={() => setAsTable((v) => !v)} className="text-xs text-ink-2 underline underline-offset-2">
          {asTable ? "Grafik" : "Tablo"}
        </button>
      </figcaption>

      {asTable ? (
        <table className="tabular w-full text-sm">
          <thead className="text-left text-ink-2">
            <tr>
              <th className="py-1 font-medium">Ay</th>
              {SERIES.map((s) => (
                <th key={s.key} className="py-1 text-right font-medium">{s.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.month} className="border-t border-line">
                <td className="py-1">{r.month}</td>
                <td className="py-1 text-right">{fmtTL(r.income)}</td>
                <td className="py-1 text-right">{fmtTL(r.expense)}</td>
                <td className="py-1 text-right">{fmtTL(r.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={rows} barGap={2} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
              <CartesianGrid vertical={false} stroke="var(--gridline)" />
              <XAxis dataKey="month" tickLine={false} axisLine={{ stroke: "var(--baseline)" }}
                tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
              <YAxis tickFormatter={fmtTLCompact} tickLine={false} axisLine={false} width={64}
                tick={{ fill: "var(--text-muted)", fontSize: 12 }} />
              <Tooltip
                cursor={{ fill: "var(--gridline)", opacity: 0.5 }}
                formatter={(v: number, name: string) => [fmtTL(v), name]}
                contentStyle={{ background: "var(--surface-1)", border: "1px solid var(--border)", borderRadius: 8,
                  color: "var(--text-primary)" }}
                labelStyle={{ color: "var(--text-secondary)" }}
              />
              <Legend wrapperStyle={{ fontSize: 12, color: "var(--text-secondary)" }} />
              <Bar dataKey="income" name={SERIES[0].label} fill={SERIES[0].color} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              <Bar dataKey="expense" name={SERIES[1].label} fill={SERIES[1].color} radius={[4, 4, 0, 0]} maxBarSize={28} isAnimationActive={false} />
              <Line dataKey="net" name={SERIES[2].label} stroke={SERIES[2].color} strokeWidth={2} isAnimationActive={false}
                dot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)", fill: SERIES[2].color }} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      )}
    </figure>
  );
}
