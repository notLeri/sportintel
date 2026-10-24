import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/relevance")({
  component: lazyRouteComponent(() => import("@/pages/admin-relevance"), "RelevancePage"),
});
