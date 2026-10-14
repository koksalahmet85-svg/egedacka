import { NextResponse } from "next/server";

import { API_BASE, TOKEN_COOKIE } from "@/lib/api/server";

export async function POST(req: Request) {
  const body = await req.json();
  const res = await fetch(`${API_BASE}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  const data = await res.json();
  if (!res.ok) return NextResponse.json(data, { status: res.status });

  const out = NextResponse.json({ role: data.role });
  out.cookies.set(TOKEN_COOKIE, data.accessToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12, // backend JWT ömrüyle aynı
  });
  return out;
}
