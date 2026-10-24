import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/taxonomy")({
  component: lazyRouteComponent(() => import("@/pages/admin-taxonomy"), "TaxonomyPage"),
});
