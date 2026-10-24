import type * as Sentry from "@sentry/react";

import { AppError } from "@/shared/api";

import { beforeSend } from "./telemetry";

const ev = (): Sentry.ErrorEvent => ({
  type: undefined,
  request: { cookies: { sid: "1" }, headers: { Cookie: "sid=1" }, url: "http://x/feed" },
  user: { id: "u1", email: "a@b.c" },
});

test.each([
  [new AppError({ status: 404, code: "common.not_found", title: "x" })],
  [new AppError({ status: 409, code: "event.invalid_transition", title: "x" })],
  [AppError.network()],
])("drops expected API errors (%s)", (err) => {
  expect(beforeSend(ev(), { originalException: err })).toBeNull();
});

test("keeps 5xx and scrubs cookies, headers, email", () => {
  const err = new AppError({ status: 500, code: "common.internal", title: "x" });
  const out = beforeSend(ev(), { originalException: err });
  expect(out?.request).toEqual({ url: "http://x/feed" });
  expect(out?.user).toEqual({ id: "u1" });
});

test("keeps ordinary render errors", () => {
  expect(beforeSend(ev(), { originalException: new Error("boom") })).not.toBeNull();
});
