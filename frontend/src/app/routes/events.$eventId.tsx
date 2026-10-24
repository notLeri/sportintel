import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/events/$eventId")({
  component: lazyRouteComponent(() => import("@/pages/event"), "EventPage"),
});
