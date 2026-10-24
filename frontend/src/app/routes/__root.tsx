import type { QueryClient } from "@tanstack/react-query";
import { createRootRouteWithContext, Outlet, redirect, useLocation } from "@tanstack/react-router";

import { meQuery } from "@/entities/user";
import { isAppError } from "@/shared/api";

import { NotFoundPage } from "../errors/NotFoundPage";
import { ErrorFallback } from "../errors/PageErrorBoundary";
import { AppShell } from "../layout/AppShell";

export interface RouterContext {
  queryClient: QueryClient;
}

function Root() {
  // Экран входа — без навигации приложения.
  return useLocation().pathname === "/login" ? <Outlet /> : <AppShell />;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  beforeLoad: async ({ context, location }) => {
    const onLogin = location.pathname === "/login";
    try {
      await context.queryClient.ensureQueryData(meQuery);
    } catch (err) {
      if (isAppError(err) && err.status === 401) {
        if (onLogin) return;
        throw redirect({ to: "/login", search: { next: location.href } });
      }
      throw err; // 5xx — экран ошибки с повтором, а не вход (FE-T0.18 §13)
    }
    if (onLogin) throw redirect({ to: "/" }); // уже вошёл
  },
  component: Root,
  notFoundComponent: NotFoundPage,
  errorComponent: ({ error, reset }) => <ErrorFallback error={error} onRetry={reset} />,
});
