import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

test("profile zone differs from the device clock: offer to switch, PATCH /me", async () => {
  // часы устройства в тестах — Сан-Паулу (vitest env TZ); профиль — Москва
  const me = makeMe("editor", { timezone: "Europe/Moscow" });
  mockMe(me);
  const patches: unknown[] = [];
  server.use(
    http.patch(apiUrl("/api/v1/me"), async ({ request }) => {
      patches.push(await request.json());
      return HttpResponse.json({ ...me, timezone: "America/Sao_Paulo" });
    }),
  );
  renderApp("/feed");
  const banner = await screen.findByText(/Moscow \(GMT\+3\).*Sao Paulo \(GMT−3\)/);
  expect(banner).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Mudar para Sao Paulo (GMT−3)" }));
  await waitFor(() => expect(patches).toEqual([{ timezone: "America/Sao_Paulo" }]));
});

test("same zone as the device: no banner", async () => {
  mockMe(makeMe("editor"));
  renderApp("/feed");
  await screen.findByRole("heading", { name: "Feed" });
  expect(screen.queryByText(/relógio deste aparelho/)).toBeNull();
});
