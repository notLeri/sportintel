import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { server } from "../../../tests/setup/msw/server";

const GE = "0192f6a1-0000-7000-8000-0000000000a1";
const CNN = "0192f6a1-0000-7000-8000-0000000000b2";
const SOURCES = [
  {
    id: "0192f6a1-0000-7000-8000-0000000000a1",
    name: "ge",
    domain: "ge.globo.com",
    tier: "A",
    active: true,
  },
  {
    id: "0192f6a1-0000-7000-8000-0000000000b2",
    name: "CNN Brasil",
    domain: "cnnbrasil.com.br",
    tier: "B",
    active: true,
  },
];

function article(i: number, extra: Record<string, unknown> = {}) {
  return {
    id: `0192f6a1-0000-7000-8000-${String(i).padStart(12, "0")}`,
    title: `Notícia ${i}`,
    url: `https://ge.globo.com/n/${i}`,
    source: { id: GE, name: "ge", domain: "ge.globo.com", tier: "A" },
    published_at: "2026-10-08T12:00:00Z",
    discovered_at: "2026-10-08T12:00:00Z",
    state: "extracted",
    failure_code: null,
    manual: false,
    image_url: null,
    event_id: null,
    ...extra,
  };
}

const requests: URL[] = [];

beforeEach(() => {
  requests.length = 0;
  mockMe(makeMe("researcher"));
  server.use(
    http.get(apiUrl("/api/v1/sources"), () => HttpResponse.json({ items: SOURCES })),
    http.get(apiUrl("/api/v1/articles"), ({ request }) => {
      const url = new URL(request.url);
      requests.push(url);
      return HttpResponse.json({
        items: [
          article(1),
          article(2, { manual: true, state: "failed", failure_code: "ssrf_blocked" }),
        ],
        next_cursor: null,
      });
    }),
  );
});

test("renders rows with source, manual badge and translated failure", async () => {
  renderApp("/articles");
  expect(await screen.findByRole("link", { name: "Notícia 1" })).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  expect(screen.getByText("manual")).toBeInTheDocument();
  expect(screen.getByText("Falhou: Endereço bloqueado por segurança")).toBeInTheDocument();
});

test("source filter goes to the URL and to the request", async () => {
  const { router } = renderApp("/articles");
  await screen.findByRole("link", { name: "Notícia 1" });
  await userEvent.click(screen.getByRole("button", { name: "Fonte" }));
  await userEvent.click(await screen.findByLabelText("CNN Brasil"));
  await waitFor(() => expect(router.state.location.searchStr).toBe(`?source=${CNN}`));
  await waitFor(() => expect(requests.at(-1)?.searchParams.getAll("source")).toEqual([CNN]));
});

test("search is debounced and sent as q", async () => {
  const { router } = renderApp("/articles");
  await screen.findByRole("link", { name: "Notícia 1" });
  await userEvent.type(screen.getByRole("searchbox", { name: "Buscar" }), "sao paulo");
  await waitFor(() => expect(router.state.location.search).toMatchObject({ q: "sao paulo" }));
  await waitFor(() => expect(requests.at(-1)?.searchParams.get("q")).toBe("sao paulo"));
  expect(requests.filter((r) => r.searchParams.get("q") === "s").length).toBe(0);
});

test("empty and error states", async () => {
  server.use(
    http.get(apiUrl("/api/v1/articles"), () => HttpResponse.json({ items: [], next_cursor: null })),
  );
  renderApp("/articles");
  expect(await screen.findByText(/Nenhuma notícia encontrada/)).toBeInTheDocument();
});

test("load error offers retry", async () => {
  server.use(http.get(apiUrl("/api/v1/articles"), () => new HttpResponse("x", { status: 503 })));
  renderApp("/articles");
  expect(await screen.findByRole("button", { name: "Tentar novamente" })).toBeInTheDocument();
});
