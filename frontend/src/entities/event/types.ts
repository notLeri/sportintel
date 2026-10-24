import type { components, paths } from "@/shared/api";

export type EventListItem = components["schemas"]["EventListItem"];
export type EventDetail = components["schemas"]["EventDetail"];
export type ArticleInEvent = components["schemas"]["ArticleInEvent"];
export type RelatedEvent = components["schemas"]["RelatedEvent"];
export type EventsQueryParams = NonNullable<paths["/api/v1/events"]["get"]["parameters"]["query"]>;
export interface EventsPage {
  items: EventListItem[];
  next_cursor: string | null;
  serverTime: string | null;
}
