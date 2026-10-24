import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/autopost")({
  component: lazyRouteComponent(() => import("@/pages/autopost"), "AutopostPage"),
});
