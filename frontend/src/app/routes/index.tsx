import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

import { validateDashboardSearch } from "@/shared/routing";

export const Route = createFileRoute("/")({
  validateSearch: validateDashboardSearch,
  component: lazyRouteComponent(() => import("@/pages/dashboard"), "DashboardPage"),
});
