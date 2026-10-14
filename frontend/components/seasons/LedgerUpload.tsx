"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

interface Result {
  rows: number;
  sheets: string[];
  anomalies: number;
  replaced_rows: number;
}

export function LedgerUpload() {
  const router = useRouter();
  const [state, setState] = useState<{ busy: boolean; msg?: string; ok?: boolean }>({ busy: false });

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const fd = new FormData(e.currentTarget);
    setState({ busy: true });
    const res = await fetch("/api/backend/ledger/import", { method: "POST", body: fd });
    const body = await res.json().catch(() => ({}));
    if (!res.ok) {
      setState({ busy: false, ok: false, msg: body.detail ?? "Yükleme başarısız" });
      return;
    }
    const r = body as Result;
    setState({
      busy: false,
      ok: true,
      msg: `${r.sheets.length} sayfa, ${r.rows} satır içe aktarıldı (${r.replaced_rows} eski satır güncellendi). ${r.anomalies} veri uyarısı.`,
    });
    router.refresh(); // sunucu bileşeni yeni veriyle yeniden çizilir
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-wrap items-center gap-2 text-sm">
      <input name="file" type="file" accept=".xlsx" required className="max-w-60 text-xs" />
      <button disabled={state.busy} className="rounded-full border border-line bg-surface px-3 py-1 disabled:opacity-50">
        {state.busy ? "Yükleniyor…" : "Defteri yükle"}
      </button>
      {state.msg && <span className={state.ok ? "text-good" : "text-critical"}>{state.msg}</span>}
    </form>
  );
}
