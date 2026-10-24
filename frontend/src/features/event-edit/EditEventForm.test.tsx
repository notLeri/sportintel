import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { changedPatch, diffFields, valuesOf } from "./diffFields";

const ID = eventItem(1).id;

function detail(extra: Record<string, unknown> = {}) {
  return {
    ...eventItem(1, { title: "Título original", version: 1 }),
    summary: {
      text: "Resumo",
      translations: {},
      origin: "source",
      citations: [],
      grounding: null,
      generated_at: null,
    },
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
    draft: null,
    conflicts: [],
    ...extra,
  };
}

beforeEach(() => mockMe(makeMe("researcher")));

test("diff helpers", () => {
  const base = valuesOf(detail() as never);
  expect(changedPatch(base, { ...base, title: "Novo", sport_id: "" })).toEqual({
    title: "Novo",
    sport_id: null,
  });
  expect(changedPatch(base, { ...base, summary: "" })).toEqual({ summary: null });
  const theirs = detail({ title: "Deles", version: 2 });
  expect(diffFields(base, { ...base, title: "Meu" }, theirs as never)).toEqual([
    { field: "title", base: "Título original", mine: "Meu", theirs: "Deles" },
  ]);
});

test("sends only changed fields; 412 shows diff; overwrite uses the new version", async () => {
  let current = detail();
  const patches: { body: unknown; ifMatch: string | null }[] = [];
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(current)),
    http.patch(apiUrl(`/api/v1/events/${ID}`), async ({ request }) => {
      patches.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
      if (patches.length === 1) {
        current = detail({ title: "Título deles", version: 2 });
        return HttpResponse.json(
          { code: "common.version_conflict", title: "x", status: 412 },
          { status: 412, headers: { "Content-Type": "application/problem+json" } },
        );
      }
      current = detail({ title: "Meu título", version: 3 });
      return HttpResponse.json(current);
    }),
  );
  renderApp(`/events/${ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Editar" }));
  const form = await screen.findByRole("form", { name: "Editar evento" });
  const title = within(form).getByLabelText("Título");
  await userEvent.clear(title);
  await userEvent.type(title, "Meu título");
  await userEvent.click(within(form).getByRole("button", { name: "Salvar" }));
  const dialog = await screen.findByRole("dialog", {
    name: "O evento foi alterado por outra pessoa",
  });
  expect(dialog).toHaveTextContent("Título deles");
  await userEvent.click(within(dialog).getByRole("button", { name: "Sobrescrever" }));
  await waitFor(() => expect(patches).toHaveLength(2));
  expect(patches[0]).toEqual({ body: { title: "Meu título" }, ifMatch: '"1"' });
  expect(patches[1]?.ifMatch).toBe('"2"');
  await waitFor(() =>
    expect(screen.queryByRole("form", { name: "Editar evento" })).not.toBeInTheDocument(),
  );
});

test("updates-since-edit banner regenerates the summary", async () => {
  let hits = 0;
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () =>
      HttpResponse.json(detail({ has_updates_since_edit: true })),
    ),
    http.post(apiUrl(`/api/v1/events/${ID}/summary:regenerate`), () => {
      hits++;
      return HttpResponse.json(detail({ version: 2 }));
    }),
  );
  renderApp(`/events/${ID}`);
  await userEvent.click(await screen.findByRole("button", { name: "Regenerar resumo" }));
  await waitFor(() => expect(hits).toBe(1));
});
