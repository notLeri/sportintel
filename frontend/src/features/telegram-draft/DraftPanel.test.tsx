import { act, cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const ID = eventItem(1).id;
const DID = "0192f6a1-0000-7000-8000-0000000000d1";

beforeAll(() => {
  Range.prototype.getClientRects = () =>
    ({
      length: 0,
      item: () => null,
      [Symbol.iterator]: [][Symbol.iterator],
    }) as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
  document.elementFromPoint = () => null;
});
afterEach(() => localStorage.clear());

function detail(draft: unknown, status = "SELECTED") {
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
    conflicts: [],
    draft,
  };
}

function draftDto(n: number, body: string, version = n, state = "ready") {
  return {
    id: DID,
    event_id: ID,
    state,
    failure_code: null,
    version,
    auto: false,
    current: {
      n,
      body_tg_html: body,
      image_url: null,
      disclaimer_kinds: ["unconfirmed"],
      disclaimer_removed: false,
      disclaimer_text: "⚠️ Aviso",
      origin: n === 1 ? "template" : "human",
      citations: [],
      grounding: null,
      author_id: null,
      created_at: "2026-01-01T10:00:00Z",
      plain_length: body.length,
      max_length: 4096,
    },
    versions: [{ n, origin: "template", author_id: null, created_at: "2026-10-09T10:00:00Z" }],
    channels: [],
  };
}

function serve(opts: { hasDraft?: boolean; patch?: () => Response } = {}) {
  let current = draftDto(1, "<b>Título</b>\n\nTexto [1]");
  let draftExists = Boolean(opts.hasDraft);
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () =>
      HttpResponse.json(
        detail(
          draftExists
            ? { id: DID, state: "ready", current_version: 1, updated_at: "2026-10-09T10:00:00Z" }
            : null,
        ),
      ),
    ),
    http.post(apiUrl(`/api/v1/events/${ID}/drafts`), () => {
      draftExists = true;
      return HttpResponse.json(current, { status: 201 });
    }),
    http.get(apiUrl(`/api/v1/drafts/${DID}`), () => HttpResponse.json(current)),
    http.patch(apiUrl(`/api/v1/drafts/${DID}`), async ({ request }) => {
      if (opts.patch) return opts.patch();
      const b = (await request.json()) as { body_tg_html: string };
      current = draftDto(2, b.body_tg_html, 2);
      return HttpResponse.json(current);
    }),
  );
}

beforeEach(() => mockMe(makeMe("researcher")));

const panel = () =>
  screen.findByRole("region", { name: "Rascunho do Telegram" }, { timeout: 4000 });

test("template generation shows editor, preview and template badge; save creates v2", async () => {
  serve();
  renderApp(`/events/${ID}`);
  await userEvent.click(
    await within(await panel()).findByRole("button", { name: "Gerar rascunho (modelo)" }),
  );
  const p = await panel();
  expect(await within(p).findByText("Modelo — complete o texto")).toBeInTheDocument();
  const editor = within(p).getByRole("textbox", { name: "Editor do rascunho" });
  expect(within(p).getByRole("article", { name: "Prévia do post no Telegram" })).toHaveTextContent(
    "Título",
  );
  await userEvent.click(editor);
  await userEvent.keyboard(" extra");
  await userEvent.click(within(p).getByRole("button", { name: "Salvar" }));
  expect(await screen.findByText("Rascunho salvo")).toBeInTheDocument();
  await waitFor(() => expect(within(p).getByText("v2")).toBeInTheDocument());
});

test("failed save keeps a local buffer that is offered after reopening", async () => {
  serve({ hasDraft: true, patch: () => HttpResponse.error() });
  vi.useFakeTimers({ shouldAdvanceTime: true });
  renderApp(`/events/${ID}`);
  const editor = await within(await panel()).findByRole("textbox", { name: "Editor do rascunho" });
  await userEvent.click(editor);
  await userEvent.keyboard(" rascunho local");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1100);
  });
  vi.useRealTimers();
  expect(Object.keys(localStorage).some((k) => k.startsWith(`draft:${DID}:`))).toBe(true);
  cleanup();
  renderApp(`/events/${ID}`);
  expect(await screen.findByText(/Há alterações não salvas/)).toBeInTheDocument();
});

test("412 opens the conflict dialog; image limits length to 1024; offline banner", async () => {
  serve({
    hasDraft: true,
    patch: () =>
      HttpResponse.json(
        { code: "common.version_conflict", title: "x", status: 412 },
        { status: 412, headers: { "Content-Type": "application/problem+json" } },
      ),
  });
  renderApp(`/events/${ID}`);
  const p = await panel();
  await userEvent.click(await within(p).findByRole("textbox", { name: "Editor do rascunho" }));
  await userEvent.keyboard(" x");
  await userEvent.type(within(p).getByLabelText("Imagem (URL)"), "https://img.example/a.jpg");
  expect(within(p).getByText(/\/ 1024/)).toBeInTheDocument();
  await userEvent.click(within(p).getByRole("button", { name: "Salvar" }));
  expect(
    await screen.findByRole("dialog", { name: "O rascunho foi alterado por outra pessoa" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Usar a versão do servidor" }));
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => false });
  act(() => void window.dispatchEvent(new Event("offline")));
  expect(await within(p).findByText(/Sem conexão/)).toBeInTheDocument();
  Object.defineProperty(navigator, "onLine", { configurable: true, get: () => true });
  // onlineManager TanStack Query глобальный: без события online следующие тесты остались бы офлайн
  act(() => void window.dispatchEvent(new Event("online")));
});

test("editor sees that a post in another language will not reach the channel", async () => {
  const base = draftDto(2, "<b>Título</b>", 2);
  const draft = {
    ...base,
    current: { ...base.current, lang: "ru" },
    channels: [
      { name: "Main", language: "en", active: true, blocked: "language" },
      { name: "Russo", language: "ru", active: false, blocked: null },
      { name: "Filtro", language: "ru", active: true, blocked: "filters" },
    ],
  };
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () =>
      HttpResponse.json(
        detail(
          { id: DID, state: "ready", current_version: 2, updated_at: "2026-10-09T10:00:00Z" },
          "DRAFT",
        ),
      ),
    ),
    http.get(apiUrl(`/api/v1/drafts/${DID}`), () => HttpResponse.json(draft)),
  );
  renderApp(`/events/${ID}`);
  const p = await panel();
  const notes = await within(p).findAllByRole("status", {}, { timeout: 4000 });
  expect(notes[0]).toHaveTextContent(
    "O canal «Main» publica em “Inglês”, mas este post está em “Russo”",
  );
  expect(notes[1]).toHaveTextContent("O canal «Filtro» não vai pegar este evento");
  expect(p).toHaveTextContent("Depois de “Pronto”, exatamente esta versão vai para «Russo»");
  expect(p).toHaveTextContent("(a autopostagem do canal está desligada agora)");
});

test("admin sets the post format for all posts: toggles, example from the current post", async () => {
  mockMe(makeMe("admin"));
  serve({ hasDraft: true });
  const value = {
    post_example: "",
    post_instructions: "",
    inline_links: true,
    include_emoji: true,
    include_source_link: true,
    max_hashtags: 4,
    template_also_reported: true,
    sport_emoji: { football: "⚽" },
  };
  const puts: { value: typeof value }[] = [];
  server.use(
    http.get(apiUrl("/api/v1/settings/drafts"), () =>
      HttpResponse.json({ key: "drafts", value, schema: {}, default: value }),
    ),
    http.put(apiUrl("/api/v1/settings/drafts"), async ({ request }) => {
      puts.push((await request.json()) as { value: typeof value });
      return HttpResponse.json({ key: "drafts", value, schema: {}, default: value });
    }),
  );
  renderApp(`/events/${ID}`);
  const p = await panel();
  await userEvent.click(await within(p).findByText("Formato dos posts (todos)"));
  await userEvent.click(await within(p).findByLabelText("Hashtags do torneio e dos times"));
  await userEvent.click(within(p).getByRole("button", { name: "Usar o post atual" }));
  await userEvent.click(within(p).getByRole("button", { name: "Salvar formato" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0]?.value).toMatchObject({
    max_hashtags: 0,
    post_example: "<b>Título</b>\n\nTexto [1]",
    sport_emoji: { football: "⚽" }, // остальные поля drafts не теряются
  });
});

test("editor approves the first version of a new event right in the draft", async () => {
  mockMe(
    makeMe("editor", { allowed_transitions: { DRAFT: [{ to: "READY", min_role: "editor" }] } }),
  );
  serve({ hasDraft: true });
  const approved: (string | null)[] = [];
  server.use(
    http.get(apiUrl(`/api/v1/events/${ID}`), () =>
      HttpResponse.json(
        detail(
          { id: DID, state: "ready", current_version: 1, updated_at: "2026-10-09T10:00:00Z" },
          "NEW",
        ),
      ),
    ),
    http.post(apiUrl("/api/v1/feed/*"), ({ request }) => {
      approved.push(request.headers.get("If-Match"));
      return new HttpResponse(null, { status: 204 });
    }),
  );
  renderApp(`/events/${ID}`);
  const p = await panel();
  await userEvent.click(await within(p).findByRole("button", { name: "Aprovar post" }));
  await waitFor(() => expect(approved).toEqual([`"${eventItem(1).version}"`]));
  expect(await screen.findByText("Post aprovado: status “Pronto”")).toBeInTheDocument();
});
