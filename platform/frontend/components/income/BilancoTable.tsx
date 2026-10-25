import { fmtMonthLong, fmtNum, fmtTL, PROGRAM_COLOR } from "@/lib/format";
import type { IncomeMonth, ProgramKey } from "@/lib/types/income";

type Props = { months: IncomeMonth[]; programs: { key: ProgramKey; label: string }[]; currentMonth: string };

/** Drive'daki boş "BİLANÇO" sayfasının otomatik dolu hali. */
export function BilancoTable({ months, programs, currentMonth }: Props) {
  const sum = (f: (m: IncomeMonth) => number) => months.reduce((a, m) => a + f(m), 0);
  return (
    <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-surface p-4">
      <h2 className="mb-1 font-semibold">Genel gelir tablosu (BİLANÇO)</h2>
      <p className="mb-3 text-xs text-ink-muted">Ödeme tablosundan her okumada yeniden hesaplanır.</p>
      <table className="tabular w-full min-w-[760px] text-sm">
        <thead className="text-left text-xs text-ink-2">
          <tr>
            <th className="py-2 font-medium">Ay</th>
            {programs.map((p) => (
              <th key={p.key} className="py-2 text-right font-medium">
                <span aria-hidden className="mr-1 inline-block h-2 w-2 rounded-sm" style={{ background: PROGRAM_COLOR[p.key] }} />
                {p.label}
              </th>
            ))}
            <th className="py-2 text-right font-medium">Toplam</th>
            <th className="py-2 text-right font-medium">Ödeyen</th>
            <th className="py-2 text-right font-medium">Ödemeyen</th>
            <th className="py-2 text-right font-medium">Taksit bekleyen</th>
          </tr>
        </thead>
        <tbody>
          {months.map((m) => (
            <tr key={m.month} className={`border-t border-line ${m.isFuture ? "text-ink-muted" : ""} ${m.month === currentMonth ? "font-semibold" : ""}`}>
              <td className="py-1.5">{fmtMonthLong(m.month)}{m.month === currentMonth && " (bu ay)"}</td>
              {programs.map((p) => (
                <td key={p.key} className="py-1.5 text-right">{m.isFuture ? "—" : fmtTL(m.byProgram[p.key] ?? 0)}</td>
              ))}
              <td className="py-1.5 text-right">{m.isFuture ? "—" : fmtTL(m.total)}</td>
              <td className="py-1.5 text-right">{m.isFuture ? "—" : fmtNum(m.payers)}</td>
              <td className={`py-1.5 text-right ${m.nonPayers ? "text-critical" : ""}`}>
                {m.isFuture ? "—" : m.nonPayers ? `▼ ${fmtNum(m.nonPayers)}` : "0"}
              </td>
              <td className="py-1.5 text-right">{m.isFuture ? "—" : fmtNum(m.pendingInstallments)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="border-t-2 border-[var(--baseline)] font-semibold">
            <td className="py-2">Genel toplam</td>
            {programs.map((p) => (
              <td key={p.key} className="py-2 text-right">{fmtTL(sum((m) => m.byProgram[p.key] ?? 0))}</td>
            ))}
            <td className="py-2 text-right">{fmtTL(sum((m) => m.total))}</td>
            <td colSpan={3} />
          </tr>
        </tfoot>
      </table>
    </section>
  );
}
