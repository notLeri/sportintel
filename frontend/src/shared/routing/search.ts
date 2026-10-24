// Search params маршрутов — канон CONV §11.1. Значения по умолчанию в URL не пишутся:
// валидатор оставляет поле пустым, потребитель применяет with*Defaults.
import {
  PERIODS,
  parseEnum,
  parseEnumList,
  parseIso,
  parseList,
  parsePeriod,
  parseText,
  parseUuid,
  type Period,
} from "@/shared/lib/search";

export const RELEVANCE = ["HIGH", "MEDIUM", "LOW", "IRRELEVANT"] as const;
export const RELIABILITY = ["HIGH", "MEDIUM", "LOW", "UNKNOWN"] as const;
export const EVENT_STATUS = [
  "NEW",
  "REVIEWING",
  "SELECTED",
  "DRAFT",
  "READY",
  "PUBLISHED",
  "REJECTED",
] as const;
export const ARTICLE_STATE = [
  "discovered",
  "extracted",
  "enriched",
  "clustered",
  "failed",
] as const;
export type Relevance = (typeof RELEVANCE)[number];
export type Reliability = (typeof RELIABILITY)[number];
export type EventStatus = (typeof EVENT_STATUS)[number];
export type ArticleState = (typeof ARTICLE_STATE)[number];

// Пустые и невалидные значения — явный undefined, а не удаление ключа: TanStack сливает сырой
// search с результатом валидатора, и удалённый ключ «протёк» бы сырым (`next=//evil.com`).
// В URL undefined не пишется (stringifySearchObject).
const omitEmpty = <T extends object>(o: T): T =>
  Object.fromEntries(
    Object.entries(o).map(([k, v]) => [k, Array.isArray(v) && v.length === 0 ? undefined : v]),
  ) as T;

function period(raw: Record<string, unknown>): { period?: Period; from?: string; to?: string } {
  const p = raw.period === undefined ? undefined : parsePeriod(raw.period);
  if (p !== "custom") return { period: p === "24h" ? undefined : p };
  return { period: p, from: parseIso(raw.from), to: parseIso(raw.to) };
}

// --- Dashboard `/` ---
export interface DashboardSearch {
  sport?: string[];
  region?: string[];
  competition?: string[];
  relevance?: Relevance[];
  reliability?: Reliability[];
  source?: string[];
  /** Исключённые источники: скрыть события только из них (повторный клик по источнику). */
  xsource?: string[];
  status?: EventStatus[];
  period?: Period;
  from?: string;
  to?: string;
  q?: string;
  entity?: string[];
  conflicts?: "1";
  sort?: "rank" | "recent";
  event?: string;
}

export function validateDashboardSearch(raw: Record<string, unknown>): DashboardSearch {
  const sort = parseEnum(raw.sort, ["rank", "recent"] as const);
  // `relevance=` (пусто) — пользователь снял все уровни: сохраняем [] вместо default.
  const noRelevance =
    raw.relevance === "" || (Array.isArray(raw.relevance) && raw.relevance.length === 0);
  const out: DashboardSearch = omitEmpty({
    sport: parseList(raw.sport),
    region: parseList(raw.region),
    competition: parseList(raw.competition),
    relevance: parseEnumList(raw.relevance, RELEVANCE),
    reliability: parseEnumList(raw.reliability, RELIABILITY),
    source: parseList(raw.source),
    xsource: parseList(raw.xsource),
    status: parseEnumList(raw.status, EVENT_STATUS),
    ...period(raw),
    q: parseText(raw.q),
    entity: parseList(raw.entity),
    conflicts: raw.conflicts === "1" || raw.conflicts === 1 ? "1" : undefined,
    sort: sort === "rank" ? undefined : sort,
    event: parseUuid(raw.event),
  });
  return noRelevance ? { ...out, relevance: [] } : out;
}

export const DASHBOARD_DEFAULTS = {
  relevance: ["HIGH", "MEDIUM", "LOW"] as Relevance[],
  status: EVENT_STATUS.filter((s) => s !== "REJECTED" && s !== "PUBLISHED") as EventStatus[],
  period: "24h" as Period,
  sort: "rank" as const,
};

export function withDashboardDefaults(s: DashboardSearch) {
  return {
    ...s,
    relevance: s.relevance ?? DASHBOARD_DEFAULTS.relevance,
    status: s.status ?? DASHBOARD_DEFAULTS.status,
    period: s.period ?? DASHBOARD_DEFAULTS.period,
    sort: s.sort ?? DASHBOARD_DEFAULTS.sort,
  };
}

// --- Feed `/feed` (ADR-004, FE-T3.15) ---
/** Фильтры, общие для «Событий» и «Ленты»: статус и период у ленты свои. */
export const FEED_FILTER_KEYS = [
  "sport",
  "region",
  "competition",
  "relevance",
  "reliability",
  "source",
  "xsource",
  "entity",
  "conflicts",
] as const;
type FeedFilterKey = (typeof FEED_FILTER_KEYS)[number];

export type FeedSearch = Pick<DashboardSearch, FeedFilterKey> & { tab?: "suggested" | "channel" };

export function validateFeedSearch(raw: Record<string, unknown>): FeedSearch {
  const tab = parseEnum(raw.tab, ["suggested", "channel"] as const);
  const all = validateDashboardSearch(raw);
  const out: FeedSearch = Object.fromEntries(
    Object.entries(all).filter(([k]) => (FEED_FILTER_KEYS as readonly string[]).includes(k)),
  );
  return { ...out, tab: tab === "suggested" ? undefined : tab };
}

// --- Articles `/articles` ---
export interface ArticlesSearch {
  source?: string[];
  state?: ArticleState[];
  period?: Period;
  from?: string;
  to?: string;
  q?: string;
}

export function validateArticlesSearch(raw: Record<string, unknown>): ArticlesSearch {
  return omitEmpty({
    source: parseList(raw.source),
    state: parseEnumList(raw.state, ARTICLE_STATE),
    ...period(raw),
    q: parseText(raw.q),
  });
}

// --- Analytics `/analytics` ---
export interface AnalyticsSearch {
  from?: string;
  to?: string;
  group_by?: "user" | "day";
}

export function validateAnalyticsSearch(raw: Record<string, unknown>): AnalyticsSearch {
  return omitEmpty({
    from: parseIso(raw.from),
    to: parseIso(raw.to),
    group_by: parseEnum(raw.group_by, ["user", "day"] as const),
  });
}

// --- Login `/login` ---
export interface LoginSearch {
  next?: string;
  error?: string;
}

/** `next` — только относительный путь приложения (защита от open redirect). */
export function validateLoginSearch(raw: Record<string, unknown>): LoginSearch {
  const next = parseText(raw.next, 2000);
  return omitEmpty({
    next: next && next.startsWith("/") && !next.startsWith("//") ? next : undefined,
    error: parseText(raw.error, 64),
  });
}

export { PERIODS };
