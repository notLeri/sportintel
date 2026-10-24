import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import type { EventDetail } from "@/entities/event";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;
const A = (n: number) => `0192f6a1-0000-7000-8000-0000000000a${n}`;

function detail(extra: Partial<EventDetail> = {}): EventDetail {
  const art = (n: number, name: string, health = "ok") => ({
    id: A(n),
    title: `Matéria ${n}`,
    url: `https://x.example.com/${n}`,
    lead: `Lead ${n}`,
    published_at: `2026-10-08T1${n}:00:00Z`,
    discovered_at: `2026-10-08T1${n}:00:00Z`,
    source: { id: A(n), name, tier: "A", owner_group: null, health },
    is_duplicate: false,
    attach_method: "auto",
    manual: false,
    relevance: "HIGH",
    clickbait: false,
    rumor_markers: n === 2 ? ["teria"] : [],
    image_url: null,
  });
  return {
    ...eventItem(1, { title: "Flamengo confirma lesão" }),
    summary: {
      text: "Pedro sofreu lesão [1] e fica fora [2].",
      translations: {},
      origin: "ai",
      citations: [
        { n: 1, article_id: A(1) },
        { n: 2, article_id: A(2) },
      ],
      grounding: null,
      generated_at: null,
    },
    relevance_rationale: "rules: lesão(+6)",
    relevance_reason: null,
    reliability_factors: [{ code: "single_tier_a", detail: "groups=globo" }],
    reliability_reason: null,
    rejection_reason: null,
    rejection_comment: null,
    manual_overrides: [],
    status_changed_at: "2026-10-08T10:00:00Z",
    created_by: null,
    teams: [{ id: A(9), name: "Flamengo" }],
    players: [],
    other_entities: [],
    articles: [art(1, "ge"), art(2, "Lance", "down")],
    related: [],
    draft: null,
    conflicts: [],
    ...extra,
  } as EventDetail;
}

function serveDetail(body: EventDetail | null) {
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () =>
      body
        ? HttpResponse.json(body, { headers: { ETag: '"1"' } })
        : HttpResponse.json(
            { code: "common.not_found", title: "nf", status: 404 },
            { status: 404, headers: { "Content-Type": "application/problem+json" } },
          ),
    ),
  );
}

beforeEach(() => mockMe(makeMe("researcher")));

test("citation highlights its source; AI mark; factors; source down; focus on title", async () => {
  serveDetail(detail());
  renderApp(`/?event=${ID}`);
  const title = await screen.findByRole("heading", { name: "Flamengo confirma lesão" });
  await waitFor(() => expect(title).toHaveFocus());
  expect(screen.getByText("Gerado por IA · não revisado")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Fonte 2: Lance" }));
  const items = within(screen.getByRole("region", { name: /2 fontes/ })).getAllByRole("listitem");
  expect(items[1]).toHaveAttribute("data-highlighted", "true");
  expect(items[0]).toHaveAttribute("data-highlighted", "false");
  expect(items[1]).toHaveTextContent("Fonte indisponível na última verificação");
  expect(items[1]).toHaveTextContent("boato");
  await userEvent.click(screen.getByText("Fatores"));
  expect(screen.getByText("Uma fonte de nível A")).toBeVisible();
});

test("human summary has no AI mark; no summary shows leads", async () => {
  serveDetail(
    detail({
      summary: {
        text: "Texto humano.",
        translations: {},
        origin: "human",
        citations: [],
        grounding: null,
        generated_at: null,
      },
    }),
  );
  renderApp(`/?event=${ID}`);
  expect(await screen.findByText("Texto humano.")).toBeInTheDocument();
  expect(screen.queryByText("Gerado por IA · não revisado")).not.toBeInTheDocument();
});

test("404 shows not found and close clears ?event", async () => {
  serveDetail(null);
  const { router } = renderApp(`/?event=${ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Fechar" }));
  await waitFor(() => expect(router.state.location.search).not.toHaveProperty("event"));
  // Без открытого события список на всю ширину — панели деталей нет.
  await waitFor(() => expect(screen.queryByRole("button", { name: "Fechar" })).toBeNull());
});

test("related events are grouped by kind", async () => {
  const rel = (n: number, kind: string) => ({
    id: `0192f6a1-0000-7000-8000-0000000000e${n}`,
    title: `Rel ${n}`,
    kind,
    relevance: "LOW",
    status: "NEW",
    last_article_at: "2026-10-08T10:00:00Z",
  });
  serveDetail(
    detail({ related: [rel(1, "related"), rel(2, "possible_duplicate"), rel(3, "old_news")] }),
  );
  renderApp(`/?event=${ID}`);
  const section = await screen.findByRole("region", { name: "Eventos relacionados" });
  for (const [group, title] of [
    ["Relacionados", "Rel 1"],
    ["Possíveis duplicados", "Rel 2"],
    ["Notícia antiga semelhante", "Rel 3"],
  ]) {
    const heading = within(section).getByRole("heading", { name: group });
    expect(heading.parentElement).toHaveTextContent(title as string);
  }
});

test("foreign source card is translated; original language is shown", async () => {
  const base = detail();
  const [first, ...rest] = base.articles ?? [];
  const es = {
    ...first,
    source: { id: A(1), name: "ge", tier: "A", owner_group: null, health: "ok", language: "es" },
    translation: { title: "Matéria traduzida", lead: "Lead traduzido" },
  } as NonNullable<EventDetail["articles"]>[number];
  serveDetail({ ...base, original_language: "es", articles: [es, ...rest] });
  renderApp(`/?event=${ID}`);
  expect(await screen.findByText("Idioma original: espanhol")).toBeInTheDocument();
  const items = within(screen.getByRole("region", { name: /2 fontes/ })).getAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Matéria traduzida");
  expect(items[0]).toHaveTextContent("Lead traduzido");
  expect(within(items[0] as HTMLElement).getByText("es")).toBeInTheDocument();
  expect(items[1]).toHaveTextContent("Matéria 2");
});

test("translation in progress is announced", async () => {
  serveDetail({ ...detail(), translation_pending: true });
  renderApp(`/?event=${ID}`);
  expect(await screen.findByRole("status", { name: "" })).toHaveTextContent("Traduzindo…");
});
