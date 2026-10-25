"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { fmtMonth, fmtTL, fmtTLCompact, PROGRAM_COLOR } from "@/lib/format";
import type { IncomeMonth, ProgramKey } from "@/lib/types/income";

type Props = { months: IncomeMonth[]; programs: { key: ProgramKey; label: string }[]; className?: string };

/** Program başına gruplu çubuk (tek eksen, TL). Sayılar alttaki BİLANÇO tablosunda da var. */
export function MonthlyIncomeChart({ months, programs, className = "" }: Props) {
  const rows = months
    .filter((m) => !m.isFuture)
    .map((m) => ({ month: fmtMonth(m.month), ...m.byProgram }));

  return (
    <figure className={`rounded-xl border border-[var(--border)] bg-surface p-4 ${className}`}>
      <figcaption className="mb-3 font-semibold">Aylık gelir (aidat ayına göre)</figcaption>
      <div className="h-72">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} barGap={2} margin={{ top: 8, right: 8, left: 8, bottom: 0 }}>
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
            {programs.map((p) => (
              <Bar key={p.key} dataKey={p.key} name={p.label} fill={PROGRAM_COLOR[p.key]} radius={[4, 4, 0, 0]}
                maxBarSize={28} isAnimationActive={false} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </figure>
  );
}
