import type { IncomeOverview } from "@/lib/types/income";

const KIND: Record<string, string> = {
  unrecognized_cell: "Tanınmayan hücre",
  missing_payment_type: "Ödeme türü eksik",
  duplicate_name: "Tekrarlayan isim",
};

type Props = {
  issues: NonNullable<IncomeOverview["issues"]>;
  total: number;
  sources: NonNullable<IncomeOverview["sources"]>;
};

/** Tablodaki veri kalitesi sorunları: düzeltildikçe bir sonraki okumada kaybolur. */
export function IssuesPanel({ issues, total, sources }: Props) {
  return (
    <details className="rounded-xl border border-[var(--border)] bg-surface p-4">
      <summary className="cursor-pointer font-semibold">
        Veri kalitesi: {total} uyarı · {sources.length} sayfa okundu
      </summary>
      <ul className="mt-3 text-xs text-ink-2">
        {sources.map((s) => (
          <li key={s.title}>{s.title}: {s.rows} satır{s.issues ? `, ${s.issues} uyarı` : ""}</li>
        ))}
      </ul>
      {issues.length > 0 && (
        <table className="mt-3 w-full text-sm">
          <thead className="text-left text-xs text-ink-2">
            <tr>
              <th className="py-1 font-medium">Sayfa</th>
              <th className="py-1 font-medium">Satır</th>
              <th className="py-1 font-medium">Sporcu</th>
              <th className="py-1 font-medium">Sorun</th>
              <th className="py-1 font-medium">Ayrıntı</th>
            </tr>
          </thead>
          <tbody>
            {issues.map((i, n) => (
              <tr key={n} className="border-t border-line">
                <td className="py-1">{i.sheet}</td>
                <td className="py-1">{i.row ?? "—"}</td>
                <td className="py-1">{i.name ?? "—"}</td>
                <td className="py-1">{KIND[i.kind] ?? i.kind}</td>
                <td className="py-1 text-ink-2">{i.detail}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </details>
  );
}
