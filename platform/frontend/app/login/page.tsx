"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

function LoginForm() {
  const router = useRouter();
  const next = useSearchParams().get("next") ?? "/gelir";
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setPending(true);
    setError(null);
    const form = new FormData(e.currentTarget);
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email: form.get("email"), password: form.get("password") }),
    });
    setPending(false);
    if (!res.ok) {
      setError((await res.json().catch(() => null))?.detail ?? "Giriş başarısız");
      return;
    }
    router.replace(next.startsWith("/") ? next : "/gelir");
  }

  return (
    <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 rounded-xl border border-[var(--border)] bg-surface p-6">
      <h1 className="text-xl font-semibold">Ege Alfa Yönetim</h1>
      <label className="block text-sm">
        E-posta
        <input name="email" type="email" required autoComplete="username"
          className="mt-1 w-full rounded-md border border-[var(--border)] bg-transparent px-3 py-2" />
      </label>
      <label className="block text-sm">
        Şifre
        <input name="password" type="password" required autoComplete="current-password"
          className="mt-1 w-full rounded-md border border-[var(--border)] bg-transparent px-3 py-2" />
      </label>
      {error && <p role="alert" className="text-sm text-critical">{error}</p>}
      <button disabled={pending} className="w-full rounded-md bg-brand px-3 py-2 font-medium text-white disabled:opacity-60">
        {pending ? "Giriş yapılıyor…" : "Giriş yap"}
      </button>
    </form>
  );
}

export default function LoginPage() {
  return (
    <main className="grid min-h-dvh place-items-center px-4">
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
