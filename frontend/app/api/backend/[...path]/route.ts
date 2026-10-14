// İstemci → FastAPI köprüsü. httpOnly cookie'deki token'ı Authorization başlığına çevirir.
// Yalnız GET: panel salt-okunur; yazma işlemleri ayrı, CSRF korumalı formlardan yapılır.
import { cookies } from "next/headers";
import { NextResponse, type NextRequest } from "next/server";

import { AUTH_COOKIE } from "@/lib/api";

const API = process.env.API_INTERNAL_URL ?? "http://localhost:8000/api/v1";

export async function GET(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Oturum yok" }, { status: 401 });

  const upstream = await fetch(`${API}/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: req.signal, // tarayıcı iptal ederse FastAPI isteği de kesilir
    cache: "no-store",
  });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "content-type": upstream.headers.get("content-type") ?? "application/json",
      "cache-control": upstream.headers.get("cache-control") ?? "no-store",
    },
  });
}
