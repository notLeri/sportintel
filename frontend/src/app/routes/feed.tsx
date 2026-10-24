import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

import { validateFeedSearch } from "@/shared/routing";

export const Route = createFileRoute("/feed")({
  validateSearch: validateFeedSearch,
  component: lazyRouteComponent(() => import("@/pages/feed"), "FeedPage"),
});
