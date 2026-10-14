const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
// Intl'in compact gösterimi Node ve tarayıcı ICU sürümlerinde farklı çıktı veriyor
// ("14,0 Mn ₺" ↔ "14 Mn ₺") → SSR hydration uyuşmazlığı. Kısaltma burada deterministik yapılır.
const oneDecimal = new Intl.NumberFormat("tr-TR", { maximumFractionDigits: 1 });
function tlCompact(v: number): string {
  const a = Math.abs(v);
  if (a >= 1e6) return `${oneDecimal.format(v / 1e6)} Mn ₺`;
  if (a >= 1e3) return `${oneDecimal.format(v / 1e3)} B ₺`;
  return tl.format(v);
}
const num = new Intl.NumberFormat("tr-TR");
const pct = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 });

export const fmt = {
  tl: (v: number | null | undefined) => (v == null ? "—" : tl.format(v)),
  tlShort: (v: number | null | undefined) => (v == null ? "—" : tlCompact(v)),
  n: (v: number | null | undefined) => (v == null ? "—" : num.format(v)),
  pct: (v: number | null | undefined) => (v == null ? "—" : pct.format(v)),
  x: (v: number | null | undefined) => (v == null ? "—" : `${v.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}×`),
  month: (ym: string) =>
    new Date(`${ym}-01T00:00:00`).toLocaleDateString("tr-TR", { month: "short", year: "2-digit" }),
};
