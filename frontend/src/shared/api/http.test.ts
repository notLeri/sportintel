import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { AppError, parseRetryAfter } from "./errors";
import { api, csrfStore, setOnUnauthenticated, unwrap } from "./http";

const url = (p: string) => `${window.location.origin}${p}`;

afterEach(() => csrfStore.set(null));

test("problem+json becomes AppError with fields", async () => {
  server.use(
    http.get(url("/healthz"), () =>
      HttpResponse.json(
        {
          type: "https://sportintel/errors/common.rate_limited",
          title: "Too many requests",
          status: 429,
          code: "common.rate_limited",
          detail: "slow down",
          errors: [{ field: "limit", code: "too_big", message: "≤ 100" }],
          request_id: "req-42",
          current: null,
        },
        {
          status: 429,
          headers: { "Content-Type": "application/problem+json", "Retry-After": "30" },
        },
      ),
    ),
  );
  const err = await unwrap(api.GET("/healthz")).catch((e: unknown) => e);
  expect(err).toBeInstanceOf(AppError);
  const e = err as AppError;
  expect([e.status, e.code, e.requestId, e.retryAfterS]).toEqual([
    429,
    "common.rate_limited",
    "req-42",
    30,
  ]);
  expect(e.fieldErrors).toEqual([{ field: "limit", code: "too_big", message: "≤ 100" }]);
  expect(e.message).toBe("slow down");
});

test("non-JSON error (502 from proxy) → common.internal", async () => {
  server.use(http.get(url("/healthz"), () => new HttpResponse("Bad gateway", { status: 502 })));
  const e = (await unwrap(api.GET("/healthz")).catch((x: unknown) => x)) as AppError;
  expect([e.status, e.code]).toEqual([502, "common.internal"]);
});

test("401 calls onUnauthenticated", async () => {
  const handler = vi.fn();
  setOnUnauthenticated(handler);
  server.use(
    http.get(url("/healthz"), () =>
      HttpResponse.json({ code: "common.unauthenticated", title: "x" }, { status: 401 }),
    ),
  );
  await expect(unwrap(api.GET("/healthz"))).rejects.toMatchObject({ status: 401 });
  expect(handler).toHaveBeenCalledOnce();
});

test("non-GET carries X-CSRF-Token, GET does not", async () => {
  const seen: Record<string, string | null> = {};
  server.use(
    http.all(url("/healthz"), ({ request }) => {
      seen[request.method] = request.headers.get("x-csrf-token");
      return HttpResponse.json({ status: "ok", version: "1" });
    }),
  );
  csrfStore.set("tok-1");
  await unwrap(api.GET("/healthz"));
  // Тело и метод не из контракта: проверяем только middleware.
  await (api as unknown as { POST: (p: string) => Promise<unknown> }).POST("/healthz");
  expect(seen).toEqual({ GET: null, POST: "tok-1" });
});

test("network error → network.offline", async () => {
  server.use(http.get(url("/healthz"), () => HttpResponse.error()));
  await expect(unwrap(api.GET("/healthz"))).rejects.toMatchObject({
    code: "network.offline",
    status: 0,
  });
});

test("success returns data", async () => {
  server.use(http.get(url("/healthz"), () => HttpResponse.json({ status: "ok", version: "1" })));
  await expect(unwrap(api.GET("/healthz"))).resolves.toEqual({ status: "ok", version: "1" });
});

test.each([
  ["120", 120],
  [null, undefined],
  ["garbage", undefined],
])("parseRetryAfter(%j)", (h, expected) => {
  expect(parseRetryAfter(h)).toBe(expected);
});

test("parseRetryAfter HTTP-date", () => {
  const now = Date.parse("2026-10-07T12:00:00Z");
  expect(parseRetryAfter("Wed, 07 Oct 2026 12:01:00 GMT", now)).toBe(60);
});
