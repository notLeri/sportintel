import { getRouteApi } from "@tanstack/react-router";
import { useCallback } from "react";

import type { DashboardSearch } from "@/shared/routing";

const dashboard = getRouteApi("/");
const feed = getRouteApi("/feed");

/** Где стоит панель фильтров: «События» или «Лента». Фильтры общие (usePersistedFilters). */
export type FilterScope = "events" | "feed";

/** URL — единственный источник состояния фильтров страницы. Сброс не трогает то, что
 * фильтром не является: открытое событие (`event`) и вкладку ленты (`tab`). */
export function useDashboardSearch(scope: FilterScope = "events") {
  // scope у компонента не меняется — порядок хуков постоянен
  const api = scope === "feed" ? feed : dashboard;
  const search = api.useSearch() as DashboardSearch;
  const navigate = api.useNavigate();
  const set = useCallback(
    (patch: Partial<DashboardSearch>) =>
      void navigate({
        search: (prev: Record<string, unknown>) => ({ ...prev, ...patch }),
        replace: true,
      } as never),
    [navigate],
  );
  const reset = useCallback(
    () =>
      void navigate({
        search: (prev: Record<string, unknown>) => ({ event: prev.event, tab: prev.tab }),
        replace: true,
      } as never),
    [navigate],
  );
  return { search, set, reset };
}
