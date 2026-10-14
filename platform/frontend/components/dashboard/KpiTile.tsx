type Tone = "good" | "warning" | "critical";

const TONE: Record<Tone, { icon: string; label: string; cls: string }> = {
  good: { icon: "▲", label: "iyi", cls: "text-good" },
  warning: { icon: "●", label: "dikkat", cls: "text-[var(--text-secondary)]" },
  critical: { icon: "▼", label: "kritik", cls: "text-critical" },
};

/** Durum rengi asla tek başına anlam taşımaz: ikon + ekran okuyucu etiketi eşlik eder. */
export function KpiTile({ label, value, hint, tone }: { label: string; value: string; hint?: string; tone?: Tone }) {
  const t = tone ? TONE[tone] : null;
  return (
    <div className="rounded-xl border border-[var(--border)] bg-surface p-4">
      <p className="text-xs text-ink-2">{label}</p>
      <p className="mt-1 flex items-baseline gap-1.5 text-xl font-semibold">
        {t && (
          <span className={`text-xs ${t.cls}`} aria-label={t.label} title={t.label}>
            {t.icon}
          </span>
        )}
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-ink-muted">{hint}</p>}
    </div>
  );
}
