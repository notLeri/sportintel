import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin")({
  component: lazyRouteComponent(() => import("@/pages/admin"), "AdminPage"),
});
