import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;

function detail(extra: Record<string, unknown> = {}) {
  return {
    ...eventItem(1, { relevance: "MEDIUM" }),
    summary: null,
    relevance_rationale: "rules: x",
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
    draft: null,
    conflicts: [],
    ...extra,
  };
}

test("researchers do not see Ajustar", async () => {
  mockMe(makeMe("researcher"));
  server.use(http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(detail())));
  renderApp(`/events/${ID}`);
  await screen.findByRole("heading", { name: "Evento 1" });
  expect(screen.queryByRole("button", { name: "Ajustar" })).not.toBeInTheDocument();
});

test("editor sets an override with reason and clears it", async () => {
  mockMe(makeMe("editor"));
  let current = detail();
  const bodies: unknown[] = [];
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(current)),
    http.put(apiUrl(`/api/v1/events/${ID}/relevance`), async ({ request }) => {
      const b = (await request.json()) as { level: string | null; reason: string | null };
      bodies.push(b);
      current = b.level
        ? detail({
            relevance: b.level,
            relevance_origin: "human",
            relevance_reason: b.reason,
            manual_overrides: ["relevance"],
            version: 2,
          })
        : detail({ version: 3 });
      return HttpResponse.json(current);
    }),
  );
  renderApp(`/events/${ID}`);
  const [adjust] = await screen.findAllByRole("button", { name: "Ajustar" });
  await userEvent.click(adjust as HTMLElement);
  const pop = await screen.findByRole("dialog");
  await userEvent.click(within(pop).getByRole("radio", { name: "Alta" }));
  const save = within(pop).getByRole("button", { name: "Salvar" });
  expect(save).toBeDisabled();
  await userEvent.type(within(pop).getByLabelText(/Motivo/), "decisão editorial");
  await userEvent.click(save);
  expect(await screen.findByText(/Ajustado manualmente: decisão editorial/)).toBeInTheDocument();
  await userEvent.click(
    (await screen.findAllByRole("button", { name: "Ajustar" }))[0] as HTMLElement,
  );
  await userEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", { name: "Voltar ao automático" }),
  );
  await waitFor(() =>
    expect(bodies).toEqual([
      { level: "HIGH", reason: "decisão editorial" },
      { level: null, reason: null },
    ]),
  );
});
