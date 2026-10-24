import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

import { validateAnalyticsSearch } from "@/shared/routing";

export const Route = createFileRoute("/analytics")({
  validateSearch: validateAnalyticsSearch,
  component: lazyRouteComponent(() => import("@/pages/analytics"), "AnalyticsPage"),
});
