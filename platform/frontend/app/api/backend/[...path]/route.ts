import { type NextRequest, NextResponse } from "next/server";

import { API_BASE, TOKEN_COOKIE } from "@/lib/api/server";

/**
 * BFF proxy: tarayıcı → /api/backend/* → FastAPI /api/v1/*.
 * Token httpOnly çerezden eklenir; CORS gerekmez, token JS'e hiç açılmaz.
 */
async function proxy(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const token = req.cookies.get(TOKEN_COOKIE)?.value;
  if (!token) return NextResponse.json({ detail: "Oturum yok" }, { status: 401 });

  const url = `${API_BASE}/api/v1/${path.map(encodeURIComponent).join("/")}${req.nextUrl.search}`;
  const hasBody = !["GET", "HEAD"].includes(req.method);
  const upstream = await fetch(url, {
    method: req.method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      ...(hasBody ? { "Content-Type": req.headers.get("content-type") ?? "application/json" } : {}),
    },
    body: hasBody ? await req.text() : undefined,
    cache: "no-store",
    signal: AbortSignal.timeout(15000),
  }).catch(() => null);

  if (!upstream) return NextResponse.json({ detail: "API'ye ulaşılamıyor" }, { status: 502 });
  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("content-type") ?? "application/json",
      "Cache-Control": upstream.headers.get("cache-control") ?? "no-store",
    },
  });
}

export { proxy as DELETE, proxy as GET, proxy as PATCH, proxy as POST, proxy as PUT };
