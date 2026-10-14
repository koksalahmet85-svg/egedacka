import { toApiError } from "./errors";

/**
 * Tarayıcı tarafı çağrı: aynı origin'deki BFF proxy'ye (/api/backend/*) gider.
 * Proxy httpOnly çerezdeki token'ı ekler → JS token'ı hiç görmez (XSS ile çalınamaz).
 */
export async function clientFetch<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`/api/backend${path}`, {
    headers: { Accept: "application/json" },
    credentials: "same-origin",
    signal,
  });
  if (!res.ok) throw await toApiError(res);
  return res.json() as Promise<T>;
}
