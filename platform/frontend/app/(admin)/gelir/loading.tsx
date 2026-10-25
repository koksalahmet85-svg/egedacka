export default function Loading() {
  return (
    <main className="mx-auto max-w-7xl space-y-4 p-4 sm:p-6" aria-busy="true">
      <div className="h-8 w-64 animate-pulse rounded bg-line" />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-6">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="h-24 animate-pulse rounded-xl bg-line" />
        ))}
      </div>
      <div className="h-80 animate-pulse rounded-xl bg-line" />
    </main>
  );
}
