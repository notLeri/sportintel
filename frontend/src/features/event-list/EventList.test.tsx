import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { eventItem } from "../../../tests/fixtures/events";

const T = { "X-Server-Time": "2026-10-08T12:00:00Z" };

beforeEach(() => mockMe(makeMe("researcher")));

function serve(
  pages: Record<string, unknown>[],
  updates: (u: URL) => Record<string, unknown> | null = () => null,
) {
  server.use(
    http.get(apiUrl("/api/v1/events"), ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("updated_since")) {
        return HttpResponse.json(updates(url) ?? { items: [], next_cursor: null }, {
          headers: { "X-Server-Time": "2026-10-08T12:00:30Z" },
        });
      }
      const page = url.searchParams.get("cursor") ? pages[1] : pages[0];
      return page
        ? HttpResponse.json(page, { headers: T })
        : HttpResponse.json({ code: "x", status: 500, title: "x" }, { status: 500 });
    }),
  );
}

test("row shows text badges, sources and flags", async () => {
  serve([
    {
      items: [eventItem(1, { has_open_conflicts: true, stale_suspected: true })],
      next_cursor: null,
    },
  ]);
  renderApp("/");
  const row = await screen.findByRole("option", { name: /Evento 1/ });
  expect(row).toHaveTextContent("Relevância alta");
  expect(row).toHaveTextContent("3 fontes · 2 independentes");
  expect(row).toHaveTextContent("Conflito");
  expect(row).toHaveTextContent("Possivelmente antiga");
});

test("j/k move the ?event= selection", async () => {
  serve([{ items: [eventItem(1), eventItem(2), eventItem(3)], next_cursor: null }]);
  const { router } = renderApp("/");
  await screen.findByRole("option", { name: /Evento 1/ });
  await userEvent.keyboard("j");
  await waitFor(() =>
    expect(router.state.location.search).toMatchObject({ event: eventItem(1).id }),
  );
  await userEvent.keyboard("j");
  await waitFor(() =>
    expect(router.state.location.search).toMatchObject({ event: eventItem(2).id }),
  );
  await userEvent.keyboard("k");
  await waitFor(() =>
    expect(router.state.location.search).toMatchObject({ event: eventItem(1).id }),
  );
  expect(screen.getByRole("option", { name: /Evento 1/ })).toHaveAttribute("aria-selected", "true");
});

test("empty state clears filters", async () => {
  serve([{ items: [], next_cursor: null }]);
  const { router } = renderApp("/?sport=football");
  const section = await screen.findByRole("region", { name: "Eventos" });
  await userEvent.click(await within(section).findByRole("button", { name: "Limpar filtros" }));
  await waitFor(() => expect(router.state.location.href).toBe("/"));
});

test("next page error offers retry", async () => {
  serve([{ items: [eventItem(1)], next_cursor: "c1" }]);
  renderApp("/");
  expect(await screen.findByText("Erro ao carregar mais eventos")).toBeInTheDocument();
});

test("polling: known events update in place, new ones go to the badge", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    serve([{ items: [eventItem(1), eventItem(2)], next_cursor: null }], () => ({
      items: [
        eventItem(1, { title: "Evento 1 atualizado", version: 2 }),
        eventItem(9, { title: "Recém-chegado" }),
      ],
      next_cursor: null,
    }));
    renderApp("/");
    await screen.findByRole("option", { name: /Evento 1/ });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(31_000);
    });
    expect(await screen.findByRole("option", { name: /Evento 1 atualizado/ })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: /Recém-chegado/ })).not.toBeInTheDocument();
    const badge = await screen.findByRole("button", { name: "1 novo evento" });
    await userEvent.click(badge);
    await waitFor(() =>
      expect(screen.queryByRole("button", { name: "1 novo evento" })).not.toBeInTheDocument(),
    );
  } finally {
    vi.useRealTimers();
  }
});
