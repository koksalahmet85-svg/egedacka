import { fmtNum, fmtPct } from "@/lib/format";
import type { FunnelBlock } from "@/lib/types/dashboard";

/** Kohort hunisi: tek renk tonu, aşama ilerledikçe koyulaşır (ordinal rampa). */
export function FunnelChart({ funnel, className = "" }: { funnel: FunnelBlock; className?: string }) {
  const steps = [
    { label: "Lead", value: funnel.leads, rate: null, color: "var(--seq-1)" },
    { label: "Ulaşıldı", value: funnel.contacted, rate: funnel.contactRate, color: "var(--seq-2)" },
    { label: "Deneme planlandı", value: funnel.trialScheduled, rate: funnel.trialBookRate, color: "var(--seq-3)" },
    { label: "Denemeye geldi", value: funnel.trialAttended, rate: funnel.trialShowRate, color: "var(--seq-4)" },
    { label: "Üye oldu", value: funnel.won, rate: funnel.trialToMemberRate, color: "var(--seq-5)" },
  ];
  const max = Math.max(funnel.leads, 1);

  return (
    <figure className={`rounded-xl border border-[var(--border)] bg-surface p-4 ${className}`}>
      <figcaption className="mb-3 flex items-baseline justify-between">
        <span className="font-semibold">Lead → üye hunisi</span>
        <span className="text-xs text-ink-2">Toplam dönüşüm {fmtPct(funnel.leadToMemberRate)}</span>
      </figcaption>
      <ol className="space-y-2.5">
        {steps.map((s) => (
          <li key={s.label} title={`${s.label}: ${fmtNum(s.value)}`}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-ink-2">{s.label}</span>
              <span className="tabular">
                <strong className="font-semibold">{fmtNum(s.value)}</strong>
                {s.rate != null && <span className="ml-2 text-ink-muted">önceki adımın {fmtPct(s.rate)}</span>}
              </span>
            </div>
            <div className="h-3 rounded bg-line">
              <div className="h-3 rounded" style={{ width: `${(s.value / max) * 100}%`, background: s.color }} />
            </div>
          </li>
        ))}
      </ol>
    </figure>
  );
}
