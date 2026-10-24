import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

import { validateLoginSearch } from "@/shared/routing";

export const Route = createFileRoute("/login")({
  validateSearch: validateLoginSearch,
  component: lazyRouteComponent(() => import("@/pages/login"), "LoginPage"),
});
