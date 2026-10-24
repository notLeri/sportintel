import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;

const DETAIL = {
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
  articles: [],
  related: [],
  conflicts: [],
  draft: null,
};

const BRIEF = {
  event_id: ID,
  lang: "pt-BR",
  brief: {
    headline: "Pedro está fora do clássico",
    status: "reported",
    summary: ["Exames confirmaram a lesão."],
    affected: ["Flamengo"],
    impact: "O ataque perde o titular no clássico.",
    actions: ["Acompanhar a escalação oficial"],
    source_refs: [1],
  },
  sources: [{ n: 1, name: "ge", tier: "A", url: "https://ge.globo.com/x" }],
  tg_html: "<b>Pedro está fora do clássico</b>",
  provider: "ollama",
  model: "qwen3:14b",
  created_at: "2026-10-09T10:00:00Z",
  stale: false,
};

beforeEach(() => mockMe(makeMe("researcher")));

test(
  "after Generate the brief appears without reloading the page",
  { timeout: 15_000 },
  async () => {
    let ready = false;
    server.use(
      http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(DETAIL)),
      http.get(apiUrl(`/api/v1/events/${ID}/briefs/:lang`), () =>
        ready
          ? HttpResponse.json(BRIEF)
          : HttpResponse.json(
              { status: 404, code: "common.not_found", title: "Not found" },
              { status: 404 },
            ),
      ),
      http.post(apiUrl(`/api/v1/events/${ID}/briefs/en\\:generate`), () => {
        ready = true; // модель «ответит» к следующему опросу
        return HttpResponse.json({ queued: true }, { status: 202 });
      }),
    );
    renderApp(`/events/${ID}`);
    await userEvent.click(await screen.findByRole("button", { name: "Gerar" }));
    expect(
      await screen.findAllByText("Pedro está fora do clássico", {}, { timeout: 10_000 }),
    ).toHaveLength(2); // карточка брифа + превью Telegram
    expect(screen.getByText("Noticiado por um veículo")).toBeInTheDocument();
  },
);
