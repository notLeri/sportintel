import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;
const OTHER = eventItem(2, { title: "Outro evento", article_count: 4 });
const ART = "0192f6a1-0000-7000-8000-0000000000a1";

function detail(extra: Record<string, unknown> = {}) {
  return {
    ...eventItem(1),
    summary: null,
    relevance_rationale: "",
    relevance_reason: null,
    reliability_factors: [],
    reliability_reason: null,
    rejection_reason: null,
    rejection_comment: null,
    manual_overrides: [],
    status_changed_at: "2026-10-08T10:00:00Z",
    created_by: null,
    teams: [],
    players: [],
    other_entities: [],
    related: [],
    draft: null,
    conflicts: [],
    articles: [
      {
        id: ART,
        title: "Matéria 1",
        url: "https://x.example/1",
        lead: null,
        published_at: null,
        discovered_at: "2026-10-08T10:00:00Z",
        source: { id: ART, name: "ge", tier: "A", owner_group: null, health: "ok" },
        is_duplicate: false,
        attach_method: "auto",
        manual: false,
        relevance: "HIGH",
        clickbait: false,
        rumor_markers: [],
        image_url: null,
      },
    ],
    ...extra,
  };
}

beforeEach(() => mockMe(makeMe("researcher")));

test("merge: picker excludes the current event, warns and confirms", async () => {
  const merges: unknown[] = [];
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(detail())),
    http.get(apiUrl("/api/v1/events"), () =>
      HttpResponse.json({ items: [eventItem(1), OTHER], next_cursor: null }),
    ),
    http.post(apiUrl(`/api/v1/events/${ID}/merge`), async ({ request }) => {
      merges.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
      return HttpResponse.json(detail({ article_count: 5, version: 2 }));
    }),
  );
  renderApp(`/events/${ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Mesclar com…" }));
  const dialog = await screen.findByRole("dialog", { name: "Mesclar evento" });
  await userEvent.type(within(dialog).getByLabelText("Buscar evento…"), "evento");
  const options = await within(dialog).findAllByRole("option");
  expect(options.map((o) => o.textContent)).toEqual(["Outro evento · 4"]);
  await userEvent.click(options[0] as HTMLElement);
  expect(within(dialog).getByRole("alert")).toHaveTextContent("serão movidas para este");
  await userEvent.click(within(dialog).getByRole("button", { name: "Mesclar" }));
  await waitFor(() =>
    expect(merges).toEqual([{ body: { other_event_id: OTHER.id }, ifMatch: '"1"' }]),
  );
  expect(await screen.findByText("Eventos mesclados")).toBeInTheDocument();
});

test("split an article into a new event", async () => {
  const moves: unknown[] = [];
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(detail())),
    http.post(apiUrl(`/api/v1/events/${ID}/articles/${ART}/move`), async ({ request }) => {
      moves.push(await request.json());
      return HttpResponse.json({
        source: detail({ articles: [], article_count: 0, version: 2 }),
        target_event_id: OTHER.id,
      });
    }),
  );
  renderApp(`/events/${ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Ações da fonte Matéria 1" }));
  await userEvent.click(await screen.findByRole("menuitem", { name: "Separar em novo evento" }));
  await waitFor(() => expect(moves).toEqual([{ target_event_id: null }]));
  expect(await screen.findByText("Fonte movida")).toBeInTheDocument();
});

test("READY events cannot be merged or have articles moved", async () => {
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(detail({ status: "READY" }))),
  );
  renderApp(`/events/${ID}`);
  expect(await screen.findByRole("button", { name: "Mesclar com…" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Ações da fonte Matéria 1" })).toBeDisabled();
});
