"use client";

// Aylık gelir vs gider (gider = operasyon + bordro, yığılmış). Tek eksen, ince çubuklar,
// 2px yüzey boşluğu, çubuk başına hover ipucu, tablo görünümü (erişilebilirlik).
import { useState } from "react";

import type { MonthlyCashflow } from "@/lib/types";

import { fmt } from "./format";

const H = 220;
const PAD = { top: 12, right: 8, bottom: 28, left: 56 };

function niceMax(v: number) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return Math.ceil(v / p) * p;
}

export function CashflowChart({ data }: { data: MonthlyCashflow[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);
  const W = 640;
  const max = niceMax(Math.max(1, ...data.map((d) => Math.max(d.income, d.expenses + d.payroll))));
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;
  const band = innerW / Math.max(1, data.length);
  const barW = Math.min(18, band / 3);
  const y = (v: number) => PAD.top + innerH - (v / max) * innerH;
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((t) => t * max);
  const active = hover != null ? data[hover] : undefined;

  return (
    <section className="rounded-xl border border-line bg-surface p-4">
      <header className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-semibold">Gelir – gider dengesi (nakit)</h2>
        <div className="flex items-center gap-4 text-xs text-ink-2">
          <Legend color="var(--series-1)" label="Tahsilat" />
          <Legend color="var(--series-2)" label="Operasyon gideri" />
          <Legend color="var(--series-3)" label="Bordro" />
          <button onClick={() => setAsTable((v) => !v)} className="rounded border border-line px-2 py-0.5">
            {asTable ? "Grafik" : "Tablo"}
          </button>
        </div>
      </header>

      {asTable ? (
        <table className="tabular w-full text-sm">
          <thead className="text-left text-ink-2">
            <tr><th>Ay</th><th className="text-right">Tahsilat</th><th className="text-right">Gider</th>
              <th className="text-right">Bordro</th><th className="text-right">Net</th></tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <tr key={d.month} className="border-t border-line">
                <td>{fmt.month(d.month)}</td><td className="text-right">{fmt.tl(d.income)}</td>
                <td className="text-right">{fmt.tl(d.expenses)}</td><td className="text-right">{fmt.tl(d.payroll)}</td>
                <td className={`text-right ${d.net < 0 ? "text-critical" : ""}`}>{fmt.tl(d.net)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="relative">
          <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" role="img"
            aria-label="Aylık tahsilat ve gider grafiği" onMouseLeave={() => setHover(null)}>
            {ticks.map((t) => (
              <g key={t}>
                <line x1={PAD.left} x2={W - PAD.right} y1={y(t)} y2={y(t)}
                  stroke={t === 0 ? "var(--axis)" : "var(--grid)"} strokeWidth={1} />
                <text x={PAD.left - 6} y={y(t)} dy="0.32em" textAnchor="end" fontSize={10} fill="var(--muted)"
                  className="tabular">{fmt.tlShort(t)}</text>
              </g>
            ))}
            {data.map((d, i) => {
              const cx = PAD.left + band * i + band / 2;
              const xi = cx - barW - 1;
              const xo = cx + 1;
              const yExp = y(d.expenses);
              const yPay = y(d.expenses + d.payroll);
              return (
                <g key={d.month}>
                  {/* hover hedefi çubuktan geniş: tüm bant */}
                  <rect x={PAD.left + band * i} y={PAD.top} width={band} height={innerH}
                    fill={hover === i ? "var(--grid)" : "transparent"} opacity={0.5}
                    onMouseEnter={() => setHover(i)} />
                  <Bar x={xi} y={y(d.income)} w={barW} h={y(0) - y(d.income)} fill="var(--series-1)" />
                  <Bar x={xo} y={yExp} w={barW} h={y(0) - yExp} fill="var(--series-2)" />
                  {/* yığın: 2px yüzey boşluğu ile ayrılmış üst segment */}
                  <Bar x={xo} y={yPay} w={barW} h={Math.max(0, yExp - yPay - 2)} fill="var(--series-3)" />
                  <text x={cx} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--muted)">
                    {fmt.month(d.month)}
                  </text>
                </g>
              );
            })}
          </svg>
          {active && hover != null && (
            <div className="pointer-events-none absolute top-2 rounded-lg border border-line bg-surface p-2 text-xs shadow-sm"
              style={{ left: `${Math.min(70, ((hover + 0.5) / data.length) * 100)}%` }}>
              <p className="font-semibold">{fmt.month(active.month)}</p>
              <p>Tahsilat: <span className="tabular">{fmt.tl(active.income)}</span></p>
              <p>Gider: <span className="tabular">{fmt.tl(active.expenses)}</span></p>
              <p>Bordro: <span className="tabular">{fmt.tl(active.payroll)}</span></p>
              <p className={active.net < 0 ? "text-critical" : "text-good"}>
                Net: <span className="tabular">{fmt.tl(active.net)}</span>
              </p>
            </div>
          )}
        </div>
      )}
    </section>
  );
}

function Bar({ x, y, w, h, fill }: { x: number; y: number; w: number; h: number; fill: string }) {
  if (h <= 0) return null;
  const r = Math.min(4, h, w / 2); // yalnız veri ucunda (üstte) yuvarlak köşe
  return (
    <path fill={fill} pointerEvents="none"
      d={`M${x},${y + h} V${y + r} Q${x},${y} ${x + r},${y} H${x + w - r} Q${x + w},${y} ${x + w},${y + r} V${y + h} Z`} />
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="inline-block size-2.5 rounded-sm" style={{ background: color }} />
      {label}
    </span>
  );
}
