const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const tlCompact = new Intl.NumberFormat("tr-TR", {
  style: "currency",
  currency: "TRY",
  notation: "compact",
  maximumFractionDigits: 1,
});
const num = new Intl.NumberFormat("tr-TR");
const pct = new Intl.NumberFormat("tr-TR", { style: "percent", maximumFractionDigits: 1 });

export const fmt = {
  tl: (v: number | null | undefined) => (v == null ? "—" : tl.format(v)),
  tlShort: (v: number | null | undefined) => (v == null ? "—" : tlCompact.format(v)),
  n: (v: number | null | undefined) => (v == null ? "—" : num.format(v)),
  pct: (v: number | null | undefined) => (v == null ? "—" : pct.format(v)),
  x: (v: number | null | undefined) => (v == null ? "—" : `${v.toLocaleString("tr-TR", { maximumFractionDigits: 1 })}×`),
  month: (ym: string) =>
    new Date(`${ym}-01T00:00:00`).toLocaleDateString("tr-TR", { month: "short", year: "2-digit" }),
};
