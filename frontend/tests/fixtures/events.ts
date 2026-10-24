import type { EventListItem } from "@/entities/event";

export function eventItem(i: number, extra: Partial<EventListItem> = {}): EventListItem {
  return {
    id: `0192f6a1-0000-7000-8000-${String(i).padStart(12, "0")}`,
    title: `Evento ${i}`,
    title_origin: "source",
    relevance: "HIGH",
    relevance_origin: "rule",
    reliability: "MEDIUM",
    reliability_origin: "rule",
    status: "NEW",
    sport_id: "football",
    region: "BR",
    title_i18n: {},
    competition: null,
    article_count: 3,
    source_count: 3,
    independent_source_count: 2,
    top_sources: [],
    occurred_at: "2026-10-08T10:00:00Z",
    last_article_at: "2026-10-08T11:00:00Z",
    updated_at: "2026-10-08T11:00:00Z",
    has_open_conflicts: false,
    has_updates_since_edit: false,
    stale_suspected: false,
    has_clickbait: false,
    assignee_id: null,
    origin: "auto",
    version: 1,
    ...extra,
  };
}
