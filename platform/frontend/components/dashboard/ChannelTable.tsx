import { CHANNEL_LABEL, fmtNum, fmtPct } from "@/lib/format";
import type { ChannelRow } from "@/lib/types/dashboard";

export function ChannelTable({ rows }: { rows: ChannelRow[] }) {
  return (
    <section className="overflow-x-auto rounded-xl border border-[var(--border)] bg-surface p-4">
      <h3 className="mb-1 font-semibold">Kanal bazlı huni</h3>
      <p className="mb-3 text-xs text-ink-muted">
        Yanıt süresi = lead geldikten ilk temasa kadar geçen medyan dakika. 15 dk üstü kırmızı işaretlenir.
      </p>
      <table className="tabular w-full min-w-[720px] text-sm">
        <thead className="text-left text-xs text-ink-2">
          <tr>
            <th className="py-2 font-medium">Kanal</th>
            <th className="py-2 text-right font-medium">Lead</th>
            <th className="py-2 text-right font-medium">Ulaşıldı</th>
            <th className="py-2 text-right font-medium">Deneme</th>
            <th className="py-2 text-right font-medium">Geldi</th>
            <th className="py-2 text-right font-medium">Üye</th>
            <th className="py-2 text-right font-medium">Kayıp</th>
            <th className="py-2 text-right font-medium">Dönüşüm</th>
            <th className="py-2 text-right font-medium">Yanıt süresi</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => {
            const slow = (r.medianResponseMin ?? 0) > 15;
            return (
              <tr key={r.channel} className="border-t border-line">
                <td className="py-2">{CHANNEL_LABEL[r.channel] ?? r.channel}</td>
                <td className="py-2 text-right">{fmtNum(r.leads)}</td>
                <td className="py-2 text-right">{fmtNum(r.contacted)}</td>
                <td className="py-2 text-right">{fmtNum(r.trialScheduled)}</td>
                <td className="py-2 text-right">{fmtNum(r.trialAttended)}</td>
                <td className="py-2 text-right">{fmtNum(r.won)}</td>
                <td className="py-2 text-right">{fmtNum(r.lost)}</td>
                <td className="py-2 text-right">{fmtPct(r.leadToMemberPct)}</td>
                <td className={`py-2 text-right ${slow ? "text-critical" : ""}`}>
                  {r.medianResponseMin == null ? "—" : `${slow ? "▼ " : ""}${fmtNum(r.medianResponseMin)} dk`}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </section>
  );
}
