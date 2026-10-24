import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { apiUrl, makeMe, mockMe, renderApp } from "../../tests/setup/render";
import { server } from "../../tests/setup/msw/server";

test("401 on /me redirects to /login with next", async () => {
  mockMe(null);
  const { router } = renderApp("/articles?q=gol");
  expect(await screen.findByRole("heading", { name: "Entrar" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/login");
  expect(router.state.location.search).toEqual({ next: "/articles?q=gol" });
});

test("5xx on /me shows retry, not login", async () => {
  server.use(http.get(apiUrl("/api/v1/me"), () => new HttpResponse("boom", { status: 503 })));
  const { router } = renderApp("/");
  expect(await screen.findByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/");
});

test("authorized user on /login goes to /", async () => {
  mockMe(makeMe("researcher"));
  const { router } = renderApp("/login");
  await screen.findByRole("heading", { name: "Eventos" });
  expect(router.state.location.pathname).toBe("/");
});

test.each([
  ["admin", true],
  ["researcher", false],
] as const)("Admin nav for %s: %s", async (role, visible) => {
  mockMe(makeMe(role));
  renderApp("/");
  const nav = await screen.findByRole("navigation", { name: "Navegação principal" });
  expect(within(nav).queryByRole("link", { name: "Admin" }) !== null).toBe(visible);
  expect(within(nav).getByText(`Ana ${role}`)).toBeInTheDocument();
});

test("logout clears cache and returns to /login", async () => {
  mockMe(makeMe("editor"));
  let csrf: string | null = null;
  server.use(
    http.post(apiUrl("/auth/logout"), ({ request }) => {
      csrf = request.headers.get("x-csrf-token");
      mockMe(null); // сессия удалена: дальше /me отвечает 401, как реальный backend
      return HttpResponse.json({ logout_url: null });
    }),
  );
  const { router, queryClient } = renderApp("/");
  await userEvent.click(await screen.findByRole("button", { name: "Menu da conta" }));
  await userEvent.click(await screen.findByRole("menuitem", { name: "Sair" }));
  await vi.waitFor(() => expect(router.state.location.pathname).toBe("/login"));
  expect(csrf).toBe("csrf-1");
  expect(queryClient.getQueryData(["user", "me"])).toBeUndefined();
});
