import { NextResponse } from "next/server";

import { AUTH_COOKIE } from "@/lib/api";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

export async function POST(req: Request) {
  const form = await req.formData();
  const res = await fetch(`${API}/auth/login`, {
    method: "POST",
    body: new URLSearchParams({ username: String(form.get("email") ?? ""), password: String(form.get("password") ?? "") }),
  });
  const next = String(form.get("next") ?? "/dashboard");
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard"; // açık yönlendirme engeli
  if (!res.ok) return NextResponse.redirect(new URL(`/login?error=1&next=${encodeURIComponent(safeNext)}`, req.url), 303);

  const { access_token } = (await res.json()) as { access_token: string };
  const out = NextResponse.redirect(new URL(safeNext, req.url), 303);
  out.cookies.set(AUTH_COOKIE, access_token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  });
  return out;
}
