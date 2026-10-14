import "server-only";

import { cookies } from "next/headers";

import { toApiError } from "./errors";

/** Sunucu tarafı (RSC / route handler) FastAPI çağrısı. Token httpOnly çerezden okunur, tarayıcıya hiç inmez. */
export const API_BASE = process.env.API_INTERNAL_URL ?? "http://localhost:8000";
export const TOKEN_COOKIE = "ea_token";

export async function serverFetch<T>(path: string, init?: RequestInit & { timeoutMs?: number }): Promise<T> {
  const token = (await cookies()).get(TOKEN_COOKIE)?.value;
  const res = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
    // Kullanıcıya özel veri: Next.js veri önbelleğine ASLA yazılmaz (rol bazlı sızıntı riski).
    cache: "no-store",
    signal: AbortSignal.timeout(init?.timeoutMs ?? 8000),
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}
