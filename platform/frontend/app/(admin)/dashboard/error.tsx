"use client";

export default function DashboardError({ reset }: { error: Error; reset: () => void }) {
  return (
    <main className="mx-auto max-w-xl p-8">
      <h1 className="text-lg font-semibold">Panel yüklenemedi</h1>
      <p className="mt-2 text-ink-2">Bağlantı geçici olarak kesilmiş olabilir.</p>
      <button onClick={reset} className="mt-4 rounded-md bg-brand px-3 py-2 text-white">
        Tekrar dene
      </button>
    </main>
  );
}
