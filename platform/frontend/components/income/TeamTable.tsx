import { fmtNum, fmtTL } from "@/lib/format";
import type { ProgramKey, TeamRow } from "@/lib/types/income";

type Props = { rows: TeamRow[]; programs: { key: ProgramKey; label: string }[] };

export function TeamTable({ rows, programs }: Props) {
  const label = Object.fromEntries(programs.map((p) => [p.key, p.label]));
  return (
    <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-surface p-4">
      <h2 className="mb-3 font-semibold">Takım / grup kırılımı</h2>
      <table className="tabular w-full min-w-[680px] text-sm">
        <thead className="text-left text-xs text-ink-2">
          <tr>
            <th className="py-2 font-medium">Program</th>
            <th className="py-2 font-medium">Takım / grup</th>
            <th className="py-2 font-medium">Koç</th>
            <th className="py-2 text-right font-medium">Aktif sporcu</th>
            <th className="py-2 text-right font-medium">Sezon geliri</th>
            <th className="py-2 text-right font-medium">Bu ay</th>
            <th className="py-2 text-right font-medium">Bu ay ödemeyen</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={`${r.program}-${r.team}-${r.coach}`} className="border-t border-line">
              <td className="py-1.5">{label[r.program]}</td>
              <td className="py-1.5">{r.team}</td>
              <td className="py-1.5">{r.coach ?? "—"}</td>
              <td className="py-1.5 text-right">{fmtNum(r.athletes)}</td>
              <td className="py-1.5 text-right">{fmtTL(r.seasonRevenue)}</td>
              <td className="py-1.5 text-right">{fmtTL(r.monthRevenue)}</td>
              <td className={`py-1.5 text-right ${r.dueThisMonth ? "text-critical" : ""}`}>
                {r.dueThisMonth ? `▼ ${r.dueThisMonth}` : "0"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
