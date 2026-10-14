interface Props {
  label: string;
  value: string;
  hint?: string;
  tone?: "default" | "good" | "critical";
}

export function KpiTile({ label, value, hint, tone = "default" }: Props) {
  const toneClass = tone === "good" ? "text-good" : tone === "critical" ? "text-critical" : "text-ink";
  return (
    <div className="rounded-xl border border-line bg-surface p-4">
      <p className="text-sm text-ink-2">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${toneClass}`}>{value}</p>
      {hint && <p className="mt-1 text-xs text-muted">{hint}</p>}
    </div>
  );
}
