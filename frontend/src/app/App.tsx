import { RouterProvider } from "@tanstack/react-router";
import { useState } from "react";

import { setOnUnauthenticated } from "@/shared/api";

import { Providers } from "./providers";
import { createQueryClient } from "./queryClient";
import { createAppRouter } from "./router";

export function App() {
  const [queryClient] = useState(createQueryClient);
  const [router] = useState(() => {
    const r = createAppRouter(queryClient);
    // Сессия истекла во время работы: 401 на любом запросе → /login?next=<текущий путь>.
    setOnUnauthenticated(() => {
      const { pathname, href } = r.state.location;
      if (pathname === "/login") return;
      queryClient.removeQueries({ queryKey: ["user"] });
      void r.navigate({ to: "/login", search: { next: href } });
    });
    return r;
  });
  return (
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>
  );
}
