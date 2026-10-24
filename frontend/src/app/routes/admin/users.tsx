import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/users")({
  component: lazyRouteComponent(() => import("@/pages/admin-users"), "UsersPage"),
});
