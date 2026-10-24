import { useSyncExternalStore } from "react";

/** Совпадает ли медиазапрос. Без matchMedia (jsdom, старые WebView) — false. */
export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia?.(query);
      m?.addEventListener("change", cb);
      return () => m?.removeEventListener("change", cb);
    },
    () => window.matchMedia?.(query).matches ?? false,
    () => false,
  );
}
