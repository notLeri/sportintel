import { createFileRoute, redirect } from "@tanstack/react-router";

// Каналы переехали во вкладку «Автопостинг»: старые ссылки ведут туда.
export const Route = createFileRoute("/admin/channels")({
  beforeLoad: () => {
    throw redirect({ to: "/autopost" });
  },
});
