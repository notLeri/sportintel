import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ALLOWED = {
  NEW: [{ to: "REJECTED", min_role: "researcher" as const }],
  DRAFT: [{ to: "READY", min_role: "editor" as const }],
  READY: [{ to: "PUBLISHED", min_role: "editor" as const }],
};
const CHANNEL = {
  id: "0192f6a1-0000-7000-8000-0000000000c1",
  name: "Main",
  language: "en",
  active: true,
};

function item(i: number, extra: Record<string, unknown> = {}, origin = "template", lang = "en") {
  return {
    event: eventItem(i, { title: `Evento ${i}`, version: 3, ...extra }),
    title: `Evento ${i}`,
    summary: `Resumo ${i}`,
    draft: {
      id: `0192f6a1-0000-7000-8000-0000000000d${i}`,
      version_n: 1,
      origin,
      body_tg_html: `<b>Post ${i}</b>`,
      disclaimer_text: null,
      image_url: null,
      lang,
    },
    sources: [{ name: "ge", url: "https://ge.globo.com/x", tier: "A" }],
  };
}

function serve(suggested: unknown[], channel: unknown[] = []) {
  const calls: { path: string; ifMatch: string | null; body: unknown }[] = [];
  const record = async (path: string, request: Request) =>
    calls.push({
      path,
      ifMatch: request.headers.get("If-Match"),
      body: JSON.parse((await request.text()) || "null") as unknown,
    });
  server.use(
    http.get(apiUrl("/api/v1/feed"), ({ request }) =>
      HttpResponse.json({
        items: new URL(request.url).searchParams.get("tab") === "channel" ? channel : suggested,
        next_cursor: null,
        channels: [CHANNEL],
      }),
    ),
    // «:prepare» в пути MSW понимает как параметр — разбираем адрес сами
    http.post(apiUrl("/api/v1/feed/*"), async ({ request }) => {
      const action = request.url.split(":").pop() ?? "";
      if (request.url.includes(eventItem(2).id))
        return HttpResponse.json(
          {
            code: "common.validation_failed",
            title: "Validation failed",
            status: 422,
            errors: [{ field: "channel_id", code: "filters", message: "post will not be sent" }],
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        );
      await record(action, request);
      return new HttpResponse(null, { status: 204 });
    }),
  );
  return calls;
}

function nth<T>(xs: T[], i: number): T {
  const v = xs[i];
  if (v === undefined) throw new Error(`no item ${i}`);
  return v;
}

beforeEach(() => mockMe(makeMe("editor", { allowed_transitions: ALLOWED })));

test("cards show the event in the interface language, sources and the channel post", async () => {
  serve([item(1, { status: "DRAFT" }), { ...item(2), draft: null }]);
  renderApp("/feed");
  const feed = await screen.findByRole("feed");
  const posts = within(feed).getAllByRole("article", { name: /Evento/ });
  expect(posts).toHaveLength(2);
  const first = nth(posts, 0);
  // есть пост — он и есть карточка; сводка — только пока поста нет
  expect(within(first).queryByText("Resumo 1")).toBeNull();
  expect(within(nth(posts, 1)).getByText("Resumo 2")).toBeInTheDocument();
  expect(within(first).getByRole("link", { name: "ge" })).toHaveAttribute(
    "href",
    "https://ge.globo.com/x",
  );
  expect(within(first).getByText(/Post do canal · en/)).toBeInTheDocument();
  expect(
    within(first).getByRole("article", { name: "Prévia do post no Telegram" }),
  ).toHaveTextContent("Post 1");
  expect(within(first).getByRole("button", { name: "Reescrever post" })).toBeInTheDocument();
  // без поста — только «Подготовить», планировать нечего
  expect(within(nth(posts, 1)).getByRole("button", { name: "Preparar post" })).toBeInTheDocument();
  expect(within(nth(posts, 1)).queryByRole("button", { name: "Agendar" })).toBeNull();
});

test("prepare sends If-Match; schedule approves and pins in one step", async () => {
  const calls = serve([item(1, { status: "DRAFT" })]);
  renderApp("/feed");
  const post = nth(await screen.findAllByRole("article", { name: /Evento/ }), 0);
  await userEvent.click(within(post).getByRole("button", { name: "Reescrever post" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]).toMatchObject({ path: "prepare", ifMatch: '"3"', body: { mode: "template" } });

  await userEvent.click(within(post).getByRole("button", { name: "Agendar" }));
  const form = within(post).getByRole("form", { name: "Agendar" });
  expect(within(form).getByLabelText("Canal")).toHaveValue(CHANNEL.id);
  await userEvent.click(within(form).getByRole("button", { name: /Aprovar e agendar/ }));
  await waitFor(() => expect(calls).toHaveLength(2));
  expect(calls[1]).toMatchObject({
    path: "schedule",
    ifMatch: '"3"',
    body: { channel_id: CHANNEL.id },
  });
  expect(await screen.findByText(/Agendado: .*Main/)).toBeInTheDocument();
});

test("a post that the channel will not take explains why; wrong language cannot be scheduled", async () => {
  serve([item(2, { status: "DRAFT" }), item(3, {}, "template", "pt-BR")]);
  renderApp("/feed");
  const posts = await screen.findAllByRole("article", { name: /Evento/ });
  await userEvent.click(within(nth(posts, 0)).getByRole("button", { name: "Agendar" }));
  await userEvent.click(within(nth(posts, 0)).getByRole("button", { name: /Aprovar e agendar/ }));
  expect(await within(nth(posts, 0)).findByRole("alert")).toHaveTextContent("Main");
  expect(within(nth(posts, 1)).queryByRole("button", { name: "Agendar" })).toBeNull();
  expect(within(nth(posts, 1)).getByText(/Main \(en\)/)).toBeInTheDocument();
});

test("the first version of a new event is approved as is", async () => {
  const calls = serve([item(1)]);
  renderApp("/feed");
  const post = nth(await screen.findAllByRole("article", { name: /Evento/ }), 0);
  await userEvent.click(within(post).getByRole("button", { name: "Aprovar" }));
  await waitFor(() => expect(calls).toHaveLength(1));
  expect(calls[0]).toMatchObject({ path: "approve", ifMatch: '"3"' });
  expect(await screen.findByText(/Post aprovado/)).toBeInTheDocument();
});

test("reject opens the dialog; tabs switch the search param; channel shows publish", async () => {
  serve([item(1)], [item(3, { status: "READY" })]);
  const { router } = renderApp("/feed");
  const post = nth(await screen.findAllByRole("article", { name: /Evento/ }), 0);
  await userEvent.click(within(post).getByRole("button", { name: "Rejeitar" }));
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  await userEvent.click(screen.getByRole("tab", { name: "Canal" }));
  await waitFor(() => expect(router.state.location.search).toMatchObject({ tab: "channel" }));
  expect(await screen.findByRole("button", { name: "Marcar como publicado" })).toBeInTheDocument();
});

test("empty state", async () => {
  serve([]);
  renderApp("/feed");
  expect(
    await screen.findByText("Nenhum evento recente acima do limiar de importância"),
  ).toBeInTheDocument();
});

test("filters are shared with Events: a source excluded there is excluded here too", async () => {
  const me = makeMe("editor", { allowed_transitions: ALLOWED });
  mockMe(me);
  const SRC = "0192f6a1-0000-7000-8000-0000000000e1";
  localStorage.setItem(`filters:${me.id}`, JSON.stringify({ xsource: [SRC], status: ["NEW"] }));
  const queries: URLSearchParams[] = [];
  serve([item(1)]);
  server.use(
    http.get(apiUrl("/api/v1/feed"), ({ request }) => {
      queries.push(new URL(request.url).searchParams);
      return HttpResponse.json({ items: [], next_cursor: null, channels: [CHANNEL] });
    }),
  );
  const { router } = renderApp("/feed");
  expect(await screen.findByRole("complementary", { name: "Filtros" })).toBeInTheDocument();
  await waitFor(() => expect(queries.at(-1)?.getAll("source_exclude")).toEqual([SRC]));
  // фильтр, которого в ленте нет (статус событий), сохранённый выбор не теряет
  await router.navigate({ to: "/feed", search: { sport: ["football"] } });
  await waitFor(() =>
    expect(JSON.parse(localStorage.getItem(`filters:${me.id}`) ?? "{}")).toEqual({
      status: ["NEW"],
      sport: ["football"],
    }),
  );
  localStorage.clear();
});

test("AI queue: what is being written now, how many wait and how long", async () => {
  serve([item(1)]);
  server.use(
    http.get(apiUrl("/api/v1/ai/progress"), () =>
      HttpResponse.json({
        running: [
          {
            kind: "post",
            event_id: eventItem(1).id,
            title: "Evento 1",
            elapsed_s: 20,
            typical_s: 40,
          },
        ],
        queues: [
          {
            kind: "post",
            pending: 289,
            eta_s: 17_340,
            done_24h: 11,
            next: [{ event_id: eventItem(2).id, title: "Evento 2" }],
          },
          { kind: "translate", pending: 0, eta_s: 0, done_24h: 5, next: [] },
        ],
        typical_s: { post: 40 },
      }),
    ),
  );
  renderApp("/feed");
  const panel = await screen.findByRole("region", { name: "IA trabalhando" });
  expect(panel).toHaveTextContent("Escrevendo post: “Evento 1”");
  expect(panel).toHaveTextContent("Posts do feed no idioma do canal — 289 na fila");
  expect(panel).toHaveTextContent(/faltam ≈ 4 h 49 min/);
  expect(panel).toHaveTextContent("Próximos: «Evento 2»");
  expect(panel).not.toHaveTextContent("Tradução"); // пустая очередь не показывается
  expect(within(panel).getAllByRole("progressbar")).toHaveLength(2);
  // в карточке самого события — что ИИ сейчас пишет его пост
  const card = await screen.findByRole("article", { name: "Evento 1" });
  expect(
    within(card).getByRole("progressbar", { name: "A IA está escrevendo o post deste evento" }),
  ).toBeInTheDocument();
});
