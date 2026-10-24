import type { components } from "@/shared/api";

export type ArticleListItem = components["schemas"]["ArticleListItem"];
export type ManualArticleAccepted = components["schemas"]["ManualArticleAccepted"];

export interface ArticleFilters {
  source: string[];
  state: string[];
  from?: string;
  to?: string;
  q?: string;
}
