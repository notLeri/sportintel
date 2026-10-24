import { useLocation, useMatches, useRouter } from "@tanstack/react-router";
import { useEffect } from "react";

import { stringifySearchObject } from "@/shared/lib/search";

type Validator = (raw: Record<string, unknown>) => Record<string, unknown>;

/**
 * Невалидные search params молча отбрасываются (FE-T0.8 §11) и URL нормализуется без новой
 * записи истории. TanStack сливает сырой search с результатом валидатора, поэтому каноническую
 * форму считаем сами: валидатор листового маршрута по сырому search.
 */
export function useCanonicalSearch(): void {
  const router = useRouter();
  const location = useLocation();
  const leafRouteId = useMatches({ select: (m) => m.at(-1)?.routeId });

  useEffect(() => {
    if (!leafRouteId) return;
    const route = router.routesById[leafRouteId as keyof typeof router.routesById];
    const validate = (route?.options as { validateSearch?: Validator } | undefined)?.validateSearch;
    const raw = location.search as Record<string, unknown>;
    const canonical = stringifySearchObject(typeof validate === "function" ? validate(raw) : {});
    if (canonical !== location.searchStr) {
      const hash = location.hash ? `#${location.hash}` : "";
      router.history.replace(`${location.pathname}${canonical}${hash}`);
    }
  }, [leafRouteId, location.search, location.searchStr, location.pathname, location.hash, router]);
}
