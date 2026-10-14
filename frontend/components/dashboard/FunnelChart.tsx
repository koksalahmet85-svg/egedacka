// Dönüşüm hunisi: sıralı aşamalar → tek renk tonu açıktan koyuya (ordinal).
// Aşamalar arası dönüşüm oranı etiketle verilir; en büyük kayıp vurgulanır (aksiyon noktası).
import type { ExecutiveSummary, FunnelStage } from "@/lib/types";

import { fmt } from "./format";

const LABELS: Record<FunnelStage, string> = {
  LEAD: "Lead",
  CONTACTED: "Ulaşıldı",
  TRIAL_BOOKED: "Deneme planlandı",
  TRIAL_ATTENDED: "Denemeye geldi",
  WON: "Kayıt oldu",
};

export function FunnelChart({ funnel }: { funnel: ExecutiveSummary["marketing"]["funnel"] }) {
  const top = funnel[0]?.count || 1;
  const steps = funnel.map((s, i) => ({ ...s, rate: i === 0 ? null : s.count / (funnel[i - 1]?.count || 1) }));
  const worst = steps.slice(1).reduce<number | null>(
    (w, s, i) => (w == null || (s.rate ?? 1) < (steps[w]?.rate ?? 1) ? i + 1 : w), null);

  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <h2 className="mb-3 font-semibold">Reklam → kayıt hunisi</h2>
      <ol className="space-y-2">
        {steps.map((s, i) => (
          <li key={s.stage} className="grid grid-cols-[8.5rem_1fr_5rem] items-center gap-2 text-sm">
            <span className="text-ink-2">{LABELS[s.stage]}</span>
            <span className="h-5 rounded-r" title={`${LABELS[s.stage]}: ${fmt.n(s.count)}`}
              style={{ width: `${Math.max(2, (s.count / top) * 100)}%`, background: `var(--funnel-${i + 1})` }} />
            <span className="tabular text-right">
              {fmt.n(s.count)}
              {s.rate != null && (
                <span className={`ml-1 text-xs ${i === worst ? "font-semibold text-critical" : "text-muted"}`}>
                  {fmt.pct(s.rate)}
                </span>
              )}
            </span>
          </li>
        ))}
      </ol>
      {worst != null && (
        <p className="mt-3 text-xs text-ink-2">
          ⚠ En büyük kayıp: <strong>{LABELS[steps[worst - 1]!.stage]} → {LABELS[steps[worst]!.stage]}</strong>.
          Optimizasyon önceliği bu geçiş.
        </p>
      )}
    </section>
  );
}
