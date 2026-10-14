import { NextResponse } from "next/server";

import { AUTH_COOKIE } from "@/lib/api";

export async function POST(req: Request) {
  const out = NextResponse.redirect(new URL("/login", req.url), 303);
  out.cookies.delete(AUTH_COOKIE);
  return out;
}
