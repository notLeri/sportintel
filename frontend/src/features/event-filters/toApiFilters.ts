import type { paths } from "@/shared/api";
import { periodToRange } from "@/shared/lib/datetime";
import { type DashboardSearch, withDashboardDefaults } from "@/shared/routing";

import { DEFAULT_PERIOD, DEFAULT_RELEVANCE, DEFAULT_STATUS } from "./defaults";

export type EventsQueryParams = NonNullable<paths["/api/v1/events"]["get"]["parameters"]["query"]>;

const sameSet = (a: readonly string[], b: readonly string[]) =>
  a.length === b.length && a.every((x) => b.includes(x));

/** URL → параметры GET /events. `event` не передаётся; период пересчитывается от `now` (скользящее окно). */
export function toApiFilters(search: DashboardSearch, now: Date): EventsQueryParams {
  const s = withDashboardDefaults(search);
  const list = (v?: string[]) => (v?.length ? v : undefined);
  return {
    sport: list(s.sport),
    region: list(s.region),
    competition: list(s.competition),
    relevance: s.relevance,
    reliability: list(s.reliability),
    source: list(s.source),
    source_exclude: list(s.xsource),
    status: s.status,
    entity: list(s.entity),
    conflicts: s.conflicts === "1" ? true : undefined,
    q: s.q,
    sort: s.sort,
    ...periodToRange(s.period, now, { from: s.from, to: s.to }),
  };
}

/** Сколько фильтров отличается от значений по умолчанию (для счётчика и «Limpar filtros»). */
export function activeFiltersCount(search: DashboardSearch): number {
  const s = withDashboardDefaults(search);
  return [
    Boolean(s.sport?.length),
    Boolean(s.region?.length),
    Boolean(s.competition?.length),
    !sameSet(s.relevance, DEFAULT_RELEVANCE),
    Boolean(s.reliability?.length),
    Boolean(s.source?.length || s.xsource?.length),
    !sameSet(s.status, DEFAULT_STATUS),
    s.period !== DEFAULT_PERIOD,
    s.conflicts === "1",
    Boolean(s.entity?.length),
    Boolean(s.q),
  ].filter(Boolean).length;
}

/** custom-период с from > to — запрос не отправляется (FE-T2.25 §11). */
export function periodError(search: DashboardSearch): boolean {
  return search.period === "custom" && Boolean(search.from && search.to && search.from > search.to);
}
