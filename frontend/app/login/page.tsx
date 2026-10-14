export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string; next?: string }> }) {
  const { error, next } = await searchParams;
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <form method="post" action="/api/auth/login" className="w-full max-w-sm space-y-4 rounded-xl border border-line bg-surface p-6">
        <h1 className="text-xl font-bold">
          EGE <span className="text-brand">ALFA</span> · Giriş
        </h1>
        {error && <p className="text-sm text-critical">E-posta veya şifre hatalı.</p>}
        <input type="hidden" name="next" value={next ?? "/dashboard"} />
        <label className="block text-sm">
          E-posta
          <input name="email" type="email" required autoComplete="username"
            className="mt-1 w-full rounded-md border border-line bg-page px-3 py-2" />
        </label>
        <label className="block text-sm">
          Şifre
          <input name="password" type="password" required autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-line bg-page px-3 py-2" />
        </label>
        <button className="w-full rounded-md bg-brand px-3 py-2 font-semibold text-white">Giriş yap</button>
      </form>
    </main>
  );
}
