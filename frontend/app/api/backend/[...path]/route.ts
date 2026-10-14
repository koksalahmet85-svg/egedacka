// İstemci → FastAPI köprüsü. httpOnly cookie'deki token'ı Authorization başlığına çevirir.
// GET serbest; POST yalnız izinli yollara ve aynı origin'den (CSRF koruması).
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

const POST_ALLOWED = new Set(["ledger/import"]);

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const { path } = await ctx.params;
  const joined = path.join("/");
  if (!POST_ALLOWED.has(joined)) return NextResponse.json({ detail: "İzin verilmeyen işlem" }, { status: 405 });
  // Çapraz site form gönderimini engelle: Origin, isteğin geldiği host ile aynı olmalı.
  const origin = req.headers.get("origin");
  if (!origin || new URL(origin).host !== req.headers.get("host")) {
    return NextResponse.json({ detail: "Geçersiz kaynak" }, { status: 403 });
  }
  const token = (await cookies()).get(AUTH_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Oturum yok" }, { status: 401 });

  const upstream = await fetch(`${API}/${joined}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}`, "content-type": req.headers.get("content-type") ?? "" },
    body: req.body,
    // @ts-expect-error — Node fetch akış gövdesi için gerekli
    duplex: "half",
    signal: req.signal,
  });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}
