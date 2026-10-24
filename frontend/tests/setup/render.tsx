import { QueryClient } from "@tanstack/react-query";
import { createMemoryHistory, createRouter, RouterProvider } from "@tanstack/react-router";
import { render } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { Providers } from "@/app/providers";
import { routeTree } from "@/app/routeTree.gen";
import type { Me } from "@/entities/user";
import { parseSearchString, stringifySearchObject } from "@/shared/lib/search";

import { server } from "./msw/server";

export const apiUrl = (path: string) => `${window.location.origin}${path}`;

const PERMS: Record<Me["role"], Me["permissions"]> = {
  researcher: [
    "self.read",
    "events.read",
    "events.edit",
    "events.transition",
    "events.merge",
    "drafts.write",
    "articles.read",
    "articles.create",
    "sources.read",
    "taxonomy.read",
  ],
  editor: [
    "self.read",
    "events.read",
    "events.edit",
    "events.transition",
    "events.merge",
    "events.override_assessment",
    "events.resolve_conflict",
    "drafts.write",
    "articles.read",
    "articles.create",
    "sources.read",
    "taxonomy.read",
    "audit.read",
    "analytics.read",
  ],
  admin: [
    "self.read",
    "events.read",
    "events.edit",
    "events.transition",
    "events.merge",
    "events.override_assessment",
    "events.resolve_conflict",
    "drafts.write",
    "articles.read",
    "articles.create",
    "sources.read",
    "taxonomy.read",
    "audit.read",
    "analytics.read",
    "sources.manage",
    "taxonomy.manage",
    "settings.manage",
    "users.manage",
    "pipeline.manage",
  ],
};

export function makeMe(role: Me["role"] = "editor", overrides: Partial<Me> = {}): Me {
  return {
    id: "0192f6a1-0000-7000-8000-000000000001",
    email: `${role}@corp.com`,
    display_name: `Ana ${role}`,
    role,
    locale: "pt-BR",
    timezone: "America/Sao_Paulo",
    hotkeys_enabled: true,
    csrf_token: "csrf-1",
    permissions: PERMS[role],
    allowed_transitions: {},
    flags: {},
    system_status: null,
    ...overrides,
  };
}

/** /me: пользователь или null (401). */
export function mockMe(me: Me | null) {
  server.use(
    http.get(apiUrl("/api/v1/me"), () =>
      me
        ? HttpResponse.json(me)
        : HttpResponse.json(
            { code: "common.unauthenticated", title: "Authentication required", status: 401 },
            { status: 401, headers: { "Content-Type": "application/problem+json" } },
          ),
    ),
  );
}

export function renderApp(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const history = createMemoryHistory({ initialEntries: [path] });
  const router = createRouter({
    routeTree,
    history,
    context: { queryClient },
    parseSearch: parseSearchString,
    stringifySearch: stringifySearchObject,
  });
  render(
    <Providers queryClient={queryClient}>
      <RouterProvider router={router} />
    </Providers>,
  );
  return { router, history, queryClient };
}
