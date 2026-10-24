import type { components } from "@/shared/api";

export type FeedItem = components["schemas"]["FeedItem"];
export type FeedPage = components["schemas"]["FeedPage"];
export type FeedTab = "suggested" | "channel";
/** Те же фильтры, что у «Событий» (query GET /feed). */
export interface FeedFilters {
  sport?: string[];
  region?: string[];
  competition?: string[];
  relevance?: string[];
  reliability?: string[];
  source?: string[];
  source_exclude?: string[];
  entity?: string[];
  conflicts?: boolean;
}
