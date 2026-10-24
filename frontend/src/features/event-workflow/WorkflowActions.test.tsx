import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;
const R = "researcher" as const;
const ALL = {
  NEW: [
    { to: "REVIEWING", min_role: R },
    { to: "SELECTED", min_role: R },
    { to: "REJECTED", min_role: R },
  ],
  SELECTED: [
    { to: "DRAFT", min_role: R },
    { to: "REJECTED", min_role: R },
  ],
  DRAFT: [
    { to: "READY", min_role: "editor" as const },
    { to: "REJECTED", min_role: R },
  ],
};

function detail(status: string, extra: Record<string, unknown> = {}) {
  return {
    ...eventItem(1, { status }),
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
    draft: null,
    conflicts: [],
    ...extra,
  };
}

function serve(status: string, onPost?: (body: Record<string, unknown>) => Response) {
  let current = detail(status);
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () => HttpResponse.json(current)),
    http.post(apiUrl(`/api/v1/events/${ID}/transitions`), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      if (onPost) return onPost(body);
      current = detail(String(body.to), { version: 2 });
      return HttpResponse.json(current);
    }),
  );
}

// под нагрузкой (полный прогон) карточка события рендерится дольше секунды по умолчанию
const group = () => screen.findByRole("group", { name: "Ações" }, { timeout: 4000 });

test("researcher on NEW sees Assumir/Selecionar/Rejeitar; selecting updates status", async () => {
  mockMe(makeMe("researcher", { allowed_transitions: ALL }));
  serve("NEW");
  renderApp(`/?event=${ID}`);
  const g = await group();
  expect(
    within(g)
      .getAllByRole("button")
      .map((b) => b.textContent),
  ).toEqual(["Assumir", "Selecionar", "Rejeitar"]);
  await userEvent.click(within(g).getByRole("button", { name: "Selecionar" }));
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Evento 1" }).closest("header")).toHaveTextContent(
      "Selecionado",
    ),
  );
});

test("SELECTED hides manual DRAFT; DRAFT approve disabled without ready draft", async () => {
  mockMe(makeMe("editor", { allowed_transitions: ALL }));
  serve("DRAFT");
  renderApp(`/?event=${ID}`);
  const g = await group();
  expect(within(g).getByRole("button", { name: "Aprovar" })).toBeDisabled();
});

test("reject dialog requires comment for OTHER and sends reason", async () => {
  mockMe(makeMe("researcher", { allowed_transitions: ALL }));
  const sent: Record<string, unknown>[] = [];
  serve("NEW", (b) => {
    sent.push(b);
    return HttpResponse.json(detail("REJECTED", { version: 2 }));
  });
  renderApp(`/?event=${ID}`);
  await userEvent.click(within(await group()).getByRole("button", { name: "Rejeitar" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("radio", { name: "Outro" }));
  const submit = within(dialog).getByRole("button", { name: "Rejeitar" });
  expect(submit).toBeDisabled();
  await userEvent.type(within(dialog).getByRole("textbox"), "fora do escopo");
  await userEvent.click(submit);
  await waitFor(() =>
    expect(sent).toEqual([{ to: "REJECTED", reason: "OTHER", comment: "fora do escopo" }]),
  );
});

test("409 rolls the optimistic status back", async () => {
  mockMe(makeMe("researcher", { allowed_transitions: ALL }));
  serve("NEW", () =>
    HttpResponse.json(
      { code: "event.invalid_transition", title: "x", status: 409 },
      { status: 409, headers: { "Content-Type": "application/problem+json" } },
    ),
  );
  renderApp(`/?event=${ID}`);
  await userEvent.click(within(await group()).getByRole("button", { name: "Selecionar" }));
  expect(await screen.findByText("Transição não permitida no status atual.")).toBeInTheDocument();
  expect(within(await group()).getByRole("button", { name: "Selecionar" })).toBeInTheDocument();
});
