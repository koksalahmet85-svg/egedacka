import { type NextRequest, NextResponse } from "next/server";

// Oturumsuz kullanıcıyı panel sayfalarından login'e yönlendir (yetki kontrolü backend'de).
export function middleware(req: NextRequest) {
  if (!req.cookies.get("ea_token")) {
    const url = new URL("/login", req.url);
    url.searchParams.set("next", req.nextUrl.pathname + req.nextUrl.search);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = { matcher: ["/dashboard/:path*", "/gelir/:path*"] };
