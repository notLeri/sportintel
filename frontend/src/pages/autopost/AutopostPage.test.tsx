import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const CH = {
  id: "0192f6a1-0000-7000-8000-0000000000c1",
  name: "Main",
  tg_chat_id: "-1001234567890",
  language: "en",
  mode: "approval",
  cron: "0 9,18 * * *",
  format: "single",
  max_per_run: 3,
  min_relevance: "HIGH",
  min_trust: "MEDIUM",
  min_tier: null,
  regions: [],
  sports: [],
  source_allow: [],
  source_deny: [],
  active: false,
  last_run_at: null,
  version: 4,
};
const RUN = new Date(Date.now() + 3_600_000).toISOString();

test("autopost tab: switch, next post, queue and the channel as subscribers see it", async () => {
  const admin = makeMe("admin", { locale: "ru", timezone: "UTC" });
  mockMe({ ...admin, permissions: [...admin.permissions, "channels.manage"] });
  let put: unknown = null;
  server.use(
    http.get(apiUrl("/api/v1/channels"), () =>
      HttpResponse.json({ items: [CH], token_configured: true, publish_enabled: true }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/schedule`), () =>
      HttpResponse.json({
        next_runs: [RUN],
        queue: [
          {
            run_at: RUN,
            event_ids: ["0192f6a1-0000-7000-8000-0000000000e1"],
            headline: "Pedro out",
            body_tg_html: "<b>Pedro out</b>",
          },
        ],
        posts: [
          {
            event_id: "0192f6a1-0000-7000-8000-0000000000e1",
            headline: "Pedro out",
            run_at: RUN,
            pinned: false,
            missed: false,
          },
        ],
        skipped: { no_post_in_language: 2 },
      }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/feed`), () =>
      HttpResponse.json({ live: false, reason: "private_chat_id", items: [] }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/publications`), () =>
      HttpResponse.json({
        items: [
          {
            id: "0192f6a1-0000-7000-8000-0000000000p1",
            event_id: "0192f6a1-0000-7000-8000-0000000000e0",
            status: "sent",
            lang: "en",
            body_tg_html: "<b>Earlier post</b>",
            tg_message_id: 7,
            error: null,
            created_at: "2026-10-09T10:00:00Z",
          },
        ],
      }),
    ),
    http.put(apiUrl(`/api/v1/channels/${CH.id}`), async ({ request }) => {
      put = await request.json();
      return HttpResponse.json({ ...CH, active: true, version: 5 });
    }),
  );
  renderApp("/autopost");
  const sw = await screen.findByRole("switch", { name: /Автопостинг/ });
  expect(sw).toHaveAttribute("aria-checked", "false");
  expect(await screen.findByRole("link", { name: "Pedro out" })).toBeInTheDocument();
  expect(screen.getByText(/2 события готовы, но нет поста/)).toBeInTheDocument();
  const phone = screen.getByRole("complementary", { name: "Канал в Telegram" });
  expect(await within(phone).findByText("Earlier post")).toBeInTheDocument();
  expect(within(phone).getByText("Запланировано, но автопостинг выключен")).toBeInTheDocument();
  await userEvent.click(sw);
  await waitFor(() => expect(put).toMatchObject({ active: true, name: "Main" }));
});

test("a ready post dragged onto the calendar is pinned to that time; a pinned one can be unpinned", async () => {
  const admin = makeMe("admin", { locale: "ru", timezone: "UTC" });
  mockMe({ ...admin, permissions: [...admin.permissions, "channels.manage"] });
  const EV = "0192f6a1-0000-7000-8000-0000000000e1";
  const PINNED = "0192f6a1-0000-7000-8000-0000000000e2";
  let pinned: unknown = null;
  let unpinned = false;
  server.use(
    http.get(apiUrl("/api/v1/channels"), () =>
      HttpResponse.json({ items: [CH], token_configured: true, publish_enabled: true }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/schedule`), () =>
      HttpResponse.json({
        next_runs: [RUN],
        queue: [],
        posts: [
          { event_id: EV, headline: "Pedro out", run_at: null, pinned: false, missed: false },
          { event_id: PINNED, headline: "Gabigol back", run_at: RUN, pinned: true, missed: false },
        ],
        skipped: {},
      }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/feed`), () =>
      HttpResponse.json({ live: false, reason: "private_chat_id", items: [] }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/publications`), () =>
      HttpResponse.json({ items: [] }),
    ),
    http.put(apiUrl(`/api/v1/channels/${CH.id}/pins/${EV}`), async ({ request }) => {
      pinned = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
    http.delete(apiUrl(`/api/v1/channels/${CH.id}/pins/${PINNED}`), () => {
      unpinned = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  renderApp("/autopost");
  const item = (await screen.findByRole("link", { name: "Pedro out" })).closest("li");
  expect(item).toHaveTextContent("в очереди, позже");
  const tomorrow = new Date(Date.now() + 86_400_000).toISOString().slice(0, 10);
  const cell = document.querySelector(`td[data-cell="${tomorrow} 14"]`);
  const data = { getData: () => EV, setData: () => {}, dropEffect: "", effectAllowed: "" };
  fireEvent.dragStart(item as HTMLElement, { dataTransfer: data });
  fireEvent.dragOver(cell as HTMLElement, { dataTransfer: data });
  fireEvent.drop(cell as HTMLElement, { dataTransfer: data });
  await waitFor(() => expect(pinned).toEqual({ publish_at: `${tomorrow}T14:00:00.000Z` }));
  await userEvent.click(screen.getByRole("button", { name: "Открепить: Gabigol back" }));
  await waitFor(() => expect(unpinned).toBe(true));
});

function serve(feed: object | null, extra: Parameters<typeof server.use> = []) {
  const admin = makeMe("admin", { locale: "ru", timezone: "UTC" });
  mockMe({ ...admin, permissions: [...admin.permissions, "channels.manage"] });
  server.use(
    http.get(apiUrl("/api/v1/channels"), () =>
      HttpResponse.json({ items: [CH], token_configured: true, publish_enabled: true }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/schedule`), () =>
      HttpResponse.json({
        next_runs: [RUN],
        queue: [],
        posts: [
          {
            event_id: EV,
            headline: "Pedro out",
            run_at: RUN,
            pinned: true,
            missed: false,
            pinned_by: "Ana",
          },
        ],
        skipped: {},
      }),
    ),
    http.get(apiUrl(`/api/v1/channels/${CH.id}/feed`), () =>
      feed
        ? HttpResponse.json(feed)
        : HttpResponse.json(
            { code: "common.internal", title: "boom", status: 500 },
            { status: 500, headers: { "Content-Type": "application/problem+json" } },
          ),
    ),
    ...extra,
  );
}
const EV = "0192f6a1-0000-7000-8000-0000000000e1";
const POST = {
  url: "https://t.me/br_testing/9",
  html: "<b>Gol</b> do Flamengo",
  published_at: "2026-10-09T22:30:53Z",
  edited: true,
  views: "1.2K",
  author: null,
  forwarded_from: "ge",
  photos: ["https://cdn4.telesco.pe/a.jpg", "https://cdn4.telesco.pe/b.jpg"],
  video_thumb: null,
  sticker: null,
  unsupported: false,
  reactions: [{ emoji: "🔥", count: "12" }],
  link_preview: null,
  document: null,
};

test("live channel looks like Telegram: subscribers, markup, album, reactions, views", async () => {
  serve({
    live: true,
    reason: null,
    items: [POST],
    username: "br_testing",
    title: "Brazil News",
    avatar_url: "https://cdn4.telesco.pe/ava.jpg",
    subscribers: "20.8K",
  });
  renderApp("/autopost");
  const phone = await screen.findByRole("complementary", { name: "Канал в Telegram" });
  expect(await within(phone).findByText("20.8K подписчиков")).toBeInTheDocument();
  expect(within(phone).getByRole("link", { name: "Brazil News" })).toHaveAttribute(
    "href",
    "https://t.me/br_testing",
  );
  const msg = within(phone).getByRole("article");
  expect(within(msg).getByText("Gol").tagName).toBe("B");
  expect(msg).toHaveTextContent("Переслано из ge");
  expect(msg).toHaveTextContent("🔥 12");
  expect(msg).toHaveTextContent("1.2K");
  expect(msg).toHaveTextContent("изменено");
  expect(msg.querySelectorAll("img")).toHaveLength(2);
  // кто закрепил — в списке готовых
  expect(screen.getByText(/закрепил\(а\): Ana/)).toBeInTheDocument();
});

test("feed error is shown as an error with retry, not as an empty channel", async () => {
  serve(null);
  renderApp("/autopost");
  const phone = await screen.findByRole("complementary", { name: "Канал в Telegram" });
  expect(await within(phone).findByRole("alert", {}, { timeout: 4000 })).toHaveTextContent(
    "Не удалось загрузить канал",
  );
  expect(within(phone).getByRole("button", { name: "Повторить" })).toBeInTheDocument();
  expect(within(phone).queryByText("В канале пока нет постов")).toBeNull();
});

test("check does not post; send now needs a second click; weeks can be paged", async () => {
  let sent = 0;
  serve({ live: false, reason: "private_chat_id", items: [] }, [
    http.get(apiUrl(`/api/v1/channels/${CH.id}/publications`), () =>
      HttpResponse.json({ items: [] }),
    ),
    http.post(apiUrl(`/api/v1/channels/${CH.id}:check`), () =>
      HttpResponse.json({
        title: "Main",
        username: null,
        bot_username: "si_bot",
        problem: "cannot_post",
      }),
    ),
    http.post(apiUrl(`/api/v1/channels/${CH.id}/posts/${EV}:send`), () => {
      sent += 1;
      return HttpResponse.json({ sent: 1, failed: 0, skipped: 0 });
    }),
  ]);
  renderApp("/autopost");
  await userEvent.click(await screen.findByRole("button", { name: "Проверить" }));
  expect(await screen.findByText(/без права публиковать/)).toBeInTheDocument();

  const send = screen.getByRole("button", { name: "Отправить сейчас: Pedro out" });
  await userEvent.click(send);
  expect(sent).toBe(0);
  expect(send).toHaveTextContent("Отправить?");
  await userEvent.click(send);
  await waitFor(() => expect(sent).toBe(1));

  const prev = screen.getByRole("button", { name: "Предыдущая неделя" });
  expect(prev).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Следующая неделя" }));
  expect(prev).toBeEnabled();
  expect(screen.getByRole("button", { name: "Сегодня" })).toBeInTheDocument();
});
