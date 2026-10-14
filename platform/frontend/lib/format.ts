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
