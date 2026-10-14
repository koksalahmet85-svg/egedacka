"use client";

// Dashboard veri çekme hook'u — harici kütüphane (SWR/React Query) olmadan:
//
//  1. İlk veri sunucudan gelir (initialData) → ilk boyamada spinner yok, istek şelalesi yok.
//  2. Filtre değişince önceki istek AbortController ile iptal edilir → yarış durumu
//     (eski aralığın geç gelen yanıtı yeni aralığın üstüne yazması) imkânsız.
//  3. Stale-while-revalidate: yeni veri gelene kadar eski veri ekranda kalır (isValidating).
//  4. Aralık başına bellek önbelleği: filtreler arasında geri dönüş anlık.
//  5. Arka planda yenileme yalnız sekme görünürken (visibilitychange) ve odak dönünce.
//  6. Ağ hatasında üstel geri çekilme ile en fazla 3 deneme; 401'de login'e yönlendirme.
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getExecutiveSummary } from "./api";
import type { DateRange, ExecutiveSummary } from "./types";

const REFRESH_MS = 60_000;
const MAX_RETRIES = 3;
const cache = new Map<string, { data: ExecutiveSummary; at: number }>();
const keyOf = (r: DateRange) => `${r.from}|${r.to}`;

interface State {
  data: ExecutiveSummary | null;
  error: ApiError | Error | null;
  isLoading: boolean; // hiç veri yok ve bekliyoruz
  isValidating: boolean; // veri var, arka planda tazeleniyor
}

export function useExecutiveDashboard(range: DateRange, initialData?: ExecutiveSummary) {
  const key = keyOf(range);
  if (initialData && !cache.has(keyOf(initialData.range))) {
    cache.set(keyOf(initialData.range), { data: initialData, at: Date.now() });
  }
  const [state, setState] = useState<State>(() => ({
    data: cache.get(key)?.data ?? null,
    error: null,
    isLoading: !cache.has(key),
    isValidating: false,
  }));
  const controller = useRef<AbortController | null>(null);

  const load = useCallback(
    async (opts: { force?: boolean } = {}) => {
      const hit = cache.get(key);
      if (hit && !opts.force && Date.now() - hit.at < REFRESH_MS) {
        setState({ data: hit.data, error: null, isLoading: false, isValidating: false });
        return;
      }
      controller.current?.abort();
      const ac = new AbortController();
      controller.current = ac;
      setState((s) => ({
        data: hit?.data ?? s.data, // eski veriyi göster, boş ekran yok
        error: null,
        isLoading: !hit && !s.data,
        isValidating: true,
      }));

      for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
        try {
          const data = await getExecutiveSummary(range, { signal: ac.signal });
          cache.set(key, { data, at: Date.now() });
          if (!ac.signal.aborted) setState({ data, error: null, isLoading: false, isValidating: false });
          return;
        } catch (err) {
          if (ac.signal.aborted) return; // kullanıcı filtreyi değiştirdi — sessizce bırak
          const e = err as Error;
          if (e instanceof ApiError && e.status === 401) {
            window.location.href = "/login?next=/dashboard";
            return;
          }
          // 4xx tekrar denenmez; ağ/5xx hatası denenir.
          const retryable = !(e instanceof ApiError) || e.status >= 500;
          if (!retryable || attempt === MAX_RETRIES) {
            setState((s) => ({ ...s, error: e, isLoading: false, isValidating: false }));
            return;
          }
          await new Promise((r) => setTimeout(r, 500 * 2 ** attempt));
          if (ac.signal.aborted) return;
        }
      }
    },
    // Bağımlılık bilinçli olarak yalnız `key`: range nesnesinin kimliği her render'da
    // değişebilir, from/to ise key'e gömülü.
    [key],
  );

  useEffect(() => {
    void load();
    return () => controller.current?.abort();
  }, [load]);

  useEffect(() => {
    const tick = () => document.visibilityState === "visible" && void load({ force: true });
    const id = window.setInterval(tick, REFRESH_MS);
    const onVisible = () => {
      const hit = cache.get(key);
      if (document.visibilityState === "visible" && (!hit || Date.now() - hit.at > REFRESH_MS)) void load({ force: true });
    };
    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
    };
  }, [key, load]);

  return { ...state, refresh: () => load({ force: true }) };
}
