import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = "0192f6a1-0000-7000-8000-00000000s001".replace("s", "a");
const DETAIL = {
  id: ID,
  name: "ge",
  domain: "globo.com",
  base_url: "https://ge.globo.com",
  kind: "rss",
  feed_urls: ["https://ge.globo.com/rss/"],
  parser_profile: "default",
  tier: "A",
  owner_group: "globo",
  language: "pt-BR",
  poll_interval_seconds: 300,
  min_request_gap_ms: 2000,
  content_policy: "transient_text",
  content_ttl_days: 7,
  url_keep_params: [],
  tos_notes: "",
  active: true,
  health: "ok",
  consecutive_failures: 0,
  next_poll_at: null,
  last_success_at: null,
  last_new_article_at: null,
  version: 3,
};

test("non-admin sees no access", async () => {
  mockMe(makeMe("editor"));
  renderApp("/admin/sources");
  expect(await screen.findByRole("alert")).toHaveTextContent("Sem permissão");
});

test("list shows health and 24 h counts", async () => {
  mockMe(makeMe("admin"));
  server.use(
    http.get(apiUrl("/api/v1/sources"), () =>
      HttpResponse.json({ items: [{ ...DETAIL, articles_24h: 42, health: "down" }] }),
    ),
  );
  renderApp("/admin/sources");
  const row = (await screen.findByRole("link", { name: "ge" })).closest("tr") as HTMLElement;
  expect(row).toHaveTextContent("fora do ar");
  expect(row).toHaveTextContent("42");
});

test("edit sends only changed fields with If-Match; trial fetch polls until done", async () => {
  mockMe(makeMe("admin"));
  const patches: unknown[] = [];
  let polls = 0;
  server.use(
    http.get(apiUrl(`/api/v1/sources/${ID}`), () => HttpResponse.json(DETAIL)),
    http.get(apiUrl(`/api/v1/sources/${ID}/runs`), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.patch(apiUrl(`/api/v1/sources/${ID}`), async ({ request }) => {
      patches.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
      return HttpResponse.json({ ...DETAIL, name: "ge novo", version: 4 });
    }),
    http.post(apiUrl(`/api/v1/sources/${ID}:test`), () =>
      HttpResponse.json({ test_id: "0192f6a1-0000-7000-8000-0000000000b1" }, { status: 202 }),
    ),
    http.get(apiUrl("/api/v1/sources/tests/:id"), () => {
      polls++;
      return HttpResponse.json({
        id: "0192f6a1-0000-7000-8000-0000000000b1",
        status: polls < 2 ? "pending" : "ok",
        created_at: "2026-10-09T10:00:00Z",
        feeds:
          polls < 2
            ? []
            : [
                {
                  feed_url: "https://ge.globo.com/rss/",
                  status: "ok",
                  error_code: null,
                  items: [{ url: "https://x/1", title: "Notícia teste" }],
                },
              ],
        sample: polls < 2 ? null : { title: "Notícia teste", text_chars: 1234 },
      });
    }),
  );
  renderApp(`/admin/sources/${ID}`);
  const form = await screen.findByRole("form", { name: "Fonte" });
  await waitFor(() => expect(within(form).getByLabelText("Nome")).toHaveValue("ge"));
  expect(within(form).getByLabelText("Tipo")).toBeDisabled();
  await userEvent.clear(within(form).getByLabelText("Nome"));
  await userEvent.type(within(form).getByLabelText("Nome"), "ge novo");
  await userEvent.click(within(form).getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(patches).toEqual([{ body: { name: "ge novo" }, ifMatch: '"3"' }]));
  await userEvent.click(screen.getByRole("button", { name: "Testar agora" }));
  expect((await screen.findAllByText("Notícia teste", {}, { timeout: 4000 })).length).toBe(2);
  expect(screen.getByText("1234")).toBeInTheDocument();
});

test("trust level changes right in the list", async () => {
  mockMe(makeMe("admin"));
  const patches: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/sources"), () =>
      HttpResponse.json({ items: [{ ...DETAIL, articles_24h: 1 }] }),
    ),
    http.patch(apiUrl(`/api/v1/sources/${ID}`), async ({ request }) => {
      patches.push({ body: await request.json(), ifMatch: request.headers.get("If-Match") });
      return HttpResponse.json({ ...DETAIL, tier: "C", version: 4 });
    }),
  );
  renderApp("/admin/sources");
  await userEvent.selectOptions(
    await screen.findByRole("combobox", { name: "Nível de confiança: ge" }),
    "C",
  );
  await waitFor(() => expect(patches).toEqual([{ body: { tier: "C" }, ifMatch: '"3"' }]));
});

test("choosing a type explains what it needs and picks a fitting profile", async () => {
  mockMe(makeMe("admin"));
  renderApp("/admin/sources/new");
  const form = await screen.findByRole("form", { name: "Fonte" });
  const guide = within(form).getByRole("complementary", { name: "O que este tipo exige" });
  expect(guide).toHaveTextContent("RSS ou Atom");
  await userEvent.selectOptions(within(form).getByLabelText("Tipo"), "html");
  expect(guide).toHaveTextContent("t.me/s/nome_do_canal");
  expect(within(form).getByLabelText("Perfil de extração")).toHaveValue("telegram");
  expect(within(form).getByLabelText("Endereço da página do canal")).toHaveAttribute(
    "placeholder",
    "https://t.me/s/channel_name",
  );
  await userEvent.selectOptions(within(form).getByLabelText("Tipo"), "manual");
  expect(within(form).queryByLabelText(/Endereço/)).not.toBeInTheDocument();
});
