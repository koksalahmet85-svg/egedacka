const tl = new Intl.NumberFormat("tr-TR", { style: "currency", currency: "TRY", maximumFractionDigits: 0 });
const tlCompact = new Intl.NumberFormat("tr-TR", { notation: "compact", maximumFractionDigits: 1 });
const num = new Intl.NumberFormat("tr-TR");

export const fmtTL = (v: number | null | undefined) => (v == null ? "—" : tl.format(v));
export const fmtTLCompact = (v: number) => `₺${tlCompact.format(v)}`;
export const fmtNum = (v: number | null | undefined) => (v == null ? "—" : num.format(v));
export const fmtPct = (v: number | null | undefined, digits = 1) =>
  v == null ? "—" : `${v < 0 ? "-" : ""}%${Math.abs(v).toLocaleString("tr-TR", { maximumFractionDigits: digits })}`;
export const fmtX = (v: number | null | undefined) =>
  v == null ? "—" : `${v.toLocaleString("tr-TR", { maximumFractionDigits: 2 })}×`;

const MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
export const fmtMonth = (ym: string) => {
  const [y, m] = ym.split("-");
  return `${MONTHS[Number(m) - 1] ?? m} ${y?.slice(2)}`;
};

export const CHANNEL_LABEL: Record<string, string> = {
  META_LEAD_AD: "Meta form",
  GOOGLE_LEAD_FORM: "Google form",
  WEBSITE: "Web sitesi",
  INSTAGRAM_DM: "Instagram DM",
  WHATSAPP: "WhatsApp",
  REFERRAL: "Tavsiye",
  WALK_IN: "Salona gelen",
  SCHOOL_EVENT: "Okul etkinliği",
  OTHER: "Diğer",
};

export const PROGRAM_COLOR: Record<string, string> = {
  SPOR_OKULU: "var(--series-1)",
  ALTYAPI: "var(--series-2)",
  MASA_TENISI: "var(--series-3)",
  DIGER: "var(--series-4)",
};

const MONTHS_LONG = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
  "Kasım", "Aralık"];
export const fmtMonthLong = (ym: string) => {
  const [y, m] = ym.split("-");
  return `${MONTHS_LONG[Number(m) - 1] ?? m} ${y}`;
};

export const fmtDateTime = (iso: string) =>
  new Date(iso).toLocaleString("tr-TR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
