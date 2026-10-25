import { fmtDateTime, fmtMonth, fmtTL } from "@/lib/format";
import type { IncomeChange } from "@/lib/types/income";

const STATUS: Record<string, string> = {
  PAID: "ödeme",
  SEASON_COVERED: "SEZONLUK",
  SCHOLARSHIP: "BURSLU",
  NOT_STARTED: "AYLIK",
  EMPTY: "boş",
  NOTE: "not",
};

/** Son 14 günde Drive'a işlenen değişiklikler (senkronlar arası fark). */
export function ChangesFeed({ changes, className = "" }: { changes: IncomeChange[]; className?: string }) {
  return (
    <section className={`rounded-xl border border-[var(--border)] bg-surface p-4 ${className}`}>
      <h2 className="mb-1 font-semibold">Drive&apos;a son işlenenler</h2>
      <p className="mb-3 text-xs text-ink-muted">Son 14 gün · okumalar arasındaki farklar</p>
      {changes.length === 0 ? (
        <p className="text-sm text-ink-2">Değişiklik yok.</p>
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto pr-1 text-sm">
          {changes.map((c, i) => {
            const payment = c.to === "PAID";
            const removed = c.from === "PAID" && c.to !== "PAID";
            return (
              <li key={i} className="flex items-baseline justify-between gap-3 border-b border-line pb-2">
                <span>
                  <span className="font-medium">{c.name}</span>
                  <span className="text-ink-2"> · {fmtMonth(c.month)} </span>
                  {payment ? (
                    <span className="text-good">▲ {fmtTL(c.toAmount)}{c.fromAmount ? ` (önce ${fmtTL(c.fromAmount)})` : ""}</span>
                  ) : removed ? (
                    <span className="text-critical">▼ {fmtTL(c.fromAmount)} silindi → {STATUS[c.to]}</span>
                  ) : (
                    <span className="text-ink-2">{STATUS[c.from ?? "EMPTY"]} → {STATUS[c.to]}</span>
                  )}
                </span>
                <span className="shrink-0 text-xs text-ink-muted">{fmtDateTime(c.at)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
