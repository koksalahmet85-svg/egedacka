"use client";

// Hizalanmış aylar: baz sezon ↔ hedef sezon, ay başına iki ince çubuk + hover ipucu.
import { useState } from "react";

import { fmt } from "@/components/dashboard/format";

interface Point { month: string; amount: number; payers: number }

const H = 200;
const PAD = { top: 10, right: 8, bottom: 26, left: 56 };

export function MonthBars({ base, target, baseLabel, targetLabel }: {
  base: Point[]; target: Point[]; baseLabel: string; targetLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const W = 560;
  // Hedef ayı ile 12 ay önceki baz ayı eşleşir.
  const pairs = target.map((t) => {
    const [y, m] = t.month.split("-").map(Number) as [number, number];
    const b = base.find((x) => x.month === `${y - 1}-${String(m).padStart(2, "0")}`);
    return { label: fmt.month(t.month).split(" ")[0] ?? t.month, t, b };
  });
  const max = Math.max(1, ...pairs.flatMap((p) => [p.t.amount, p.b?.amount ?? 0]));
  const p10 = 10 ** Math.floor(Math.log10(max));
  const top = Math.ceil(max / p10) * p10;
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const band = innerW / Math.max(1, pairs.length);
  const bw = Math.min(22, band / 3);
  const y = (v: number) => PAD.top + innerH - (v / top) * innerH;
  const active = hover != null ? pairs[hover] : undefined;

  return (
    <div className="relative">
      <div className="mb-2 flex gap-4 text-xs text-ink-2">
        <span className="inline-flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm" style={{ background: "var(--series-2)" }} />{baseLabel}</span>
        <span className="inline-flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm" style={{ background: "var(--series-1)" }} />{targetLabel}</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img" aria-label="Aylık tahsilat karşılaştırması"
        onMouseLeave={() => setHover(null)}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={PAD.left} x2={W - PAD.right} y1={y(f * top)} y2={y(f * top)} stroke={f ? "var(--grid)" : "var(--axis)"} />
            <text x={PAD.left - 6} y={y(f * top)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--muted)">{fmt.tlShort(f * top)}</text>
          </g>
        ))}
        {pairs.map((p, i) => {
          const cx = PAD.left + band * i + band / 2;
          const hb = y(0) - y(p.b?.amount ?? 0);
          const ht = y(0) - y(p.t.amount);
          return (
            <g key={p.t.month}>
              <rect x={PAD.left + band * i} y={PAD.top} width={band} height={innerH} fill={hover === i ? "var(--grid)" : "transparent"}
                opacity={0.5} onMouseEnter={() => setHover(i)} />
              {hb > 0 && <rect x={cx - bw - 1} y={y(p.b?.amount ?? 0)} width={bw} height={hb} rx={3} fill="var(--series-2)" pointerEvents="none" />}
              {ht > 0 && <rect x={cx + 1} y={y(p.t.amount)} width={bw} height={ht} rx={3} fill="var(--series-1)" pointerEvents="none" />}
              <text x={cx} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--muted)">{p.label}</text>
            </g>
          );
        })}
      </svg>
      {active && hover != null && (
        <div className="pointer-events-none absolute top-6 rounded-lg border border-line bg-surface p-2 text-xs shadow-sm"
          style={{ left: `${Math.min(65, ((hover + 0.5) / pairs.length) * 100)}%` }}>
          <p className="font-semibold">{active.label}</p>
          <p>{baseLabel}: <span className="tabular">{fmt.tl(active.b?.amount ?? 0)}</span> · {active.b?.payers ?? 0} kişi</p>
          <p>{targetLabel}: <span className="tabular">{fmt.tl(active.t.amount)}</span> · {active.t.payers} kişi</p>
        </div>
      )}
    </div>
  );
}
