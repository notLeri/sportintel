import { createFileRoute, lazyRouteComponent } from "@tanstack/react-router";

export const Route = createFileRoute("/admin/pipeline")({
  component: lazyRouteComponent(() => import("@/pages/admin-pipeline"), "PipelinePage"),
});
