import type { QueryClient } from "@tanstack/react-query";
import { createRouter } from "@tanstack/react-router";

import { parseSearchString, stringifySearchObject } from "@/shared/lib/search";

import { NotFoundPage } from "./errors/NotFoundPage";
import { routeTree } from "./routeTree.gen";

export function createAppRouter(queryClient: QueryClient) {
  return createRouter({
    routeTree,
    context: { queryClient },
    defaultPreload: "intent",
    defaultNotFoundComponent: NotFoundPage,
    // Списки — через запятую (`?sport=football,tennis`), а не JSON по умолчанию.
    parseSearch: parseSearchString,
    stringifySearch: stringifySearchObject,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
