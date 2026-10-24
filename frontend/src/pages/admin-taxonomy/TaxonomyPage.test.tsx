import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const E = {
  id: "0192f6a1-0000-7000-8000-0000000000e1",
  kind: "team",
  sport_id: "football",
  canonical_name: "Flamengo",
  priority: 2,
  review_state: "approved",
  active: true,
  aliases: ["Flamengo", "Mengão"],
  auto_created: false,
  version: 1,
};
const U = {
  mention_norm: "joaozinho",
  mention: "Joãozinho",
  kind: "player",
  sport_id: "football",
  sport_key: "football",
  occurrences: 7,
  first_seen_at: "2026-10-01T10:00:00Z",
  last_seen_at: "2026-10-09T10:00:00Z",
  sample_article_id: null,
};

beforeEach(() => mockMe(makeMe("admin")));

test("create an entity with aliases; canonical alias cannot be removed", async () => {
  const posts: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/taxonomy/entities/admin"), () =>
      HttpResponse.json({ items: [E], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/taxonomy/entities"), async ({ request }) => {
      posts.push(await request.json());
      return HttpResponse.json(
        { ...E, id: "0192f6a1-0000-7000-8000-0000000000e2" },
        { status: 201 },
      );
    }),
  );
  renderApp("/admin/taxonomy");
  const row = (await screen.findAllByText("Flamengo", { selector: "td span" }))[0]?.closest(
    "tr",
  ) as HTMLElement;
  expect(
    within(row).queryByRole("button", { name: "Remover apelido Flamengo" }),
  ).not.toBeInTheDocument();
  expect(within(row).getByRole("button", { name: "Remover apelido Mengão" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Nova entidade" }));
  const form = screen.getByRole("form", { name: "Nova entidade" });
  await userEvent.type(within(form).getByLabelText("Nome"), "Gabriel Barbosa");
  await userEvent.selectOptions(within(form).getByLabelText("Tipo"), "player");
  await userEvent.type(within(form).getByLabelText(/Apelidos/), "Gabigol, Gabi");
  await userEvent.click(within(form).getByRole("button", { name: "Criar" }));
  await waitFor(() =>
    expect(posts).toEqual([
      {
        kind: "player",
        sport_id: "football",
        canonical_name: "Gabriel Barbosa",
        priority: 0,
        aliases: ["Gabigol", "Gabi"],
      },
    ]),
  );
});

test("resolve unlinked: link, create, ignore", async () => {
  const actions: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/taxonomy/unlinked"), () =>
      HttpResponse.json({ items: [U], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/taxonomy/entities/admin"), () =>
      HttpResponse.json({
        items: [{ ...E, kind: "player", canonical_name: "João Silva" }],
        next_cursor: null,
      }),
    ),
    http.post(apiUrl("/api/v1/taxonomy/unlinked/:m"), async ({ request }) => {
      actions.push(await request.json());
      return HttpResponse.json({ state: "resolved", entity_id: E.id });
    }),
  );
  renderApp("/admin/taxonomy");
  await userEvent.click(await screen.findByRole("tab", { name: "Não vinculados" }));
  for (const action of ["link", "create", "ignore"] as const) {
    await userEvent.click(await screen.findByRole("button", { name: "Resolver" }));
    const d = await screen.findByRole("dialog");
    if (action === "link") {
      await userEvent.type(within(d).getByLabelText("Vincular a…"), "joao");
      await userEvent.click(await within(d).findByRole("button", { name: "João Silva" }));
      await userEvent.click(within(d).getByRole("button", { name: /^Vincular: João Silva/ }));
    } else {
      await userEvent.click(
        within(d).getByRole("button", { name: action === "create" ? "Criar entidade" : "Ignorar" }),
      );
    }
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  }
  expect(actions.map((a) => (a as { action: string }).action)).toEqual([
    "link",
    "create",
    "ignore",
  ]);
  expect((actions[0] as { entity_id: string }).entity_id).toBe(E.id);
});
