import { NextResponse } from "next/server";

import { TOKEN_COOKIE } from "@/lib/api/server";

export async function POST() {
  const out = NextResponse.json({ ok: true });
  out.cookies.delete(TOKEN_COOKIE);
  return out;
}
