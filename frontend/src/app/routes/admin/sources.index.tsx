import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/sources/")({
  component: lazyRouteComponent(() => import("@/pages/admin-sources"), "SourcesListPage"),
});
