import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

import { validateArticlesSearch } from "@/shared/routing";

export const Route = createFileRoute("/articles")({
  validateSearch: validateArticlesSearch,
  component: lazyRouteComponent(() => import("@/pages/articles"), "ArticlesPage"),
});
