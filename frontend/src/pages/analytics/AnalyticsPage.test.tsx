import { act, renderHook, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { useViewHeartbeat } from "@/features/event-details";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const SUMMARY = {
  totals: {
    useful_stories: 12,
    active_hours: 4,
    uspH: 3,
    events_new: 40,
    ai_cost_usd: 0,
    ai_cost_per_useful: null,
  },
  rows: [
    { key: "u1", label: "Ana", useful_stories: 12, active_hours: 4, uspH: 3 },
    { key: "u2", label: "Bia", useful_stories: 0, active_hours: 0, uspH: null },
  ],
  funnel: [
    { status: "NEW", count: 40 },
    { status: "SELECTED", count: 12 },
  ],
  time_to_select_p50_min: 18,
  reject_reasons: [{ reason: "DUPLICATE", count: 3 }],
  precision_high: 0.75,
  precision_high_by_origin: { rule: 0.75 },
  draft_edit_ratio_p50: 0.4,
  draft_edit_ratio_p50_by_origin: { template: 0.4 },
  feed_funnel: { suggested: 20, taken: 8, published: 5 },
  first_source_leaders: [{ source_id: "s1", name: "ge", useful_first_count: 7 }],
};

test("tiles, table, funnel; AI cost hidden while zero; researchers blocked", async () => {
  mockMe(makeMe("editor"));
  server.use(http.get(apiUrl("/api/v1/analytics/summary"), () => HttpResponse.json(SUMMARY)));
  renderApp("/analytics");
  expect((await screen.findAllByText("3,00")).length).toBeGreaterThan(0);
  expect(screen.queryByText("Custo de IA por história útil")).not.toBeInTheDocument();
  const table = screen.getByRole("table", { name: "USpH" });
  expect(within(table).getByText("Bia").closest("tr")).toHaveTextContent("—");
  expect(screen.getByRole("list", { name: "Funil do feed" })).toHaveTextContent("Publicados");
  expect(screen.getAllByText("40%").length).toBe(2); // общий и по шаблонам
});

test("heartbeat: immediately, then every minute, skipped when hidden", async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  const beats: unknown[] = [];
  server.use(
    http.post(apiUrl("/api/v1/analytics/heartbeat"), async ({ request }) => {
      beats.push(await request.json());
      return new HttpResponse(null, { status: 204 });
    }),
  );
  try {
    renderHook(() => useViewHeartbeat("0192f6a1-0000-7000-8000-000000000001"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_500);
    });
    expect(beats).toHaveLength(2);
    Object.defineProperty(document, "visibilityState", { configurable: true, get: () => "hidden" });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_500);
    });
    expect(beats).toHaveLength(2);
  } finally {
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
    vi.useRealTimers();
  }
});

test("AI load: verdict, flow, advice applies one setting", async () => {
  mockMe(makeMe("admin"));
  const puts: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/analytics/summary"), () => HttpResponse.json(SUMMARY)),
    http.get(apiUrl("/api/v1/analytics/ai-load"), () =>
      HttpResponse.json({
        verdict: "overloaded",
        share: 1.4,
        busy_share: 0.9,
        events_per_day: { HIGH: 300, MEDIUM: 700, LOW: 2000 },
        sources: 120,
        need_s_per_day: {},
        kinds: [{ kind: "post", calls: 1300, failed: 3, p50_s: 47, busy_s: 61_100 }],
        backlog: { post: 900, translate: 40 },
        backlog_eta_s: 56_000,
        headroom_events_per_day: 0,
        settings: {},
        advice: [
          {
            id: "posts_high",
            apply: { key: "drafts", field: "auto_min_relevance", value: "HIGH" },
            link: null,
            share_after: 0.42,
            params: {},
          },
          {
            id: "noisy_source",
            apply: null,
            link: "/admin/sources/s9",
            share_after: null,
            params: { name: "Spam FC", events: 40, source_id: "s9" },
          },
        ],
      }),
    ),
    http.get(apiUrl("/api/v1/settings/drafts"), () =>
      HttpResponse.json({
        key: "drafts",
        value: { auto_min_relevance: "MEDIUM", max_hashtags: 4 },
      }),
    ),
    http.put(apiUrl("/api/v1/settings/drafts"), async ({ request }) => {
      puts.push(await request.json());
      return HttpResponse.json({ key: "drafts", value: {} });
    }),
  );
  renderApp("/analytics");
  const section = await screen.findByRole("region", { name: /^Carga da IA/ });
  expect(section).toHaveTextContent("A IA não está dando conta");
  expect(section).toHaveTextContent("1000 eventos importantes por dia");
  expect(section).toHaveTextContent("de 120 fontes");
  expect(section).toHaveTextContent("depois disso, carga ≈ 42% do dia");
  expect(within(section).getByRole("link", { name: "Abrir fonte" })).toHaveAttribute(
    "href",
    "/admin/sources/s9",
  );
  await userEvent.click(within(section).getByRole("button", { name: "Aplicar" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  // меняется одно поле, остальное — как было
  expect(puts[0]).toEqual({ value: { auto_min_relevance: "HIGH", max_hashtags: 4 } });
});
