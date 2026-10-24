import { http, HttpResponse, type RequestHandler } from "msw";

const origin = () => window.location.origin;

// Общие хендлеры по умолчанию (пустые списки); тесты переопределяют через server.use(...).
export const handlers: RequestHandler[] = [
  http.get(`${origin()}/api/v1/sources`, () => HttpResponse.json({ items: [] })),
  http.get(`${origin()}/api/v1/articles`, () =>
    HttpResponse.json({ items: [], next_cursor: null }),
  ),
  http.get(`${origin()}/api/v1/taxonomy/sports`, () =>
    HttpResponse.json({
      items: [
        { id: "football", name: "Futebol", name_i18n: { "pt-BR": "Futebol" }, sort: 10 },
        { id: "volleyball", name: "Vôlei", name_i18n: { "pt-BR": "Vôlei" }, sort: 60 },
      ],
    }),
  ),
  http.get(`${origin()}/api/v1/taxonomy/entities`, () => HttpResponse.json({ items: [] })),
  http.get(`${origin()}/api/v1/events`, () =>
    HttpResponse.json(
      { items: [], next_cursor: null },
      { headers: { "X-Server-Time": "2026-10-08T12:00:00Z" } },
    ),
  ),
  http.get(`${origin()}/api/v1/feed`, () => HttpResponse.json({ items: [], next_cursor: null })),
  // ИИ ничего не делает: панели прогресса не показываются
  http.get(`${origin()}/api/v1/ai/progress`, () =>
    HttpResponse.json({ running: [], queues: [], typical_s: {} }),
  ),
  http.get(`${origin()}/api/v1/analytics/ai-load`, () =>
    HttpResponse.json({
      verdict: "off",
      share: 0,
      busy_share: 0,
      events_per_day: {},
      sources: 0,
      need_s_per_day: {},
      kinds: [],
      backlog: { post: 0, translate: 0 },
      backlog_eta_s: 0,
      headroom_events_per_day: 0,
      settings: {},
      advice: [],
    }),
  ),
  http.get(`${origin()}/api/v1/audit`, () => HttpResponse.json({ items: [], next_cursor: null })),
  http.post(
    `${origin()}/api/v1/analytics/heartbeat`,
    () => new HttpResponse(null, { status: 204 }),
  ),
];
