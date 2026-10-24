import { Outlet } from "@tanstack/react-router";

import { TimeZoneBanner } from "@/features/timezone";

import { PageErrorBoundary } from "../errors/PageErrorBoundary";
import { AppNav } from "./AppNav";
import { StatusBanner } from "./StatusBanner";
import { useCanonicalSearch } from "./useCanonicalSearch";

export function AppShell() {
  useCanonicalSearch();
  return (
    <div className="min-h-dvh md:grid md:grid-cols-[5.5rem_minmax(0,1fr)]">
      <AppNav />
      {/* Экранные страницы (data-fill-screen, дашборд) делят высоту экрана с плашкой статуса;
          остальные растут по содержимому и прокручиваются окном — полоса навигации остаётся sticky. */}
      <div className="flex min-w-0 flex-col has-[[data-fill-screen]]:h-[calc(100dvh-4rem)] md:has-[[data-fill-screen]]:h-dvh">
        <StatusBanner />
        <TimeZoneBanner />
        <main id="main" className="min-h-0 min-w-0 flex-1">
          <PageErrorBoundary>
            <Outlet />
          </PageErrorBoundary>
        </main>
      </div>
    </div>
  );
}
