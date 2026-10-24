import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/sources/$sourceId")({
  component: lazyRouteComponent(() => import("@/pages/admin-sources"), "SourceFormPage"),
});
