import * as Sentry from "@sentry/react";

import { isAppError } from "@/shared/api";
import { appEnv } from "@/shared/lib/env";

type SentryEvent = Sentry.ErrorEvent;

export function beforeSend(event: SentryEvent, hint: Sentry.EventHint): SentryEvent | null {
  const err = hint.originalException;
  // 4xx и офлайн — ожидаемые ситуации, не инциденты.
  if (isAppError(err) && (err.status < 500 || err.code === "network.offline")) return null;
  if (event.request) {
    delete event.request.cookies;
    delete event.request.headers;
  }
  if (event.user) delete event.user.email;
  return event;
}

let enabled = false;

export function initTelemetry(): boolean {
  const dsn = import.meta.env.VITE_SENTRY_DSN as string | undefined;
  if (!dsn) return false;
  Sentry.init({
    dsn,
    release: import.meta.env.VITE_VERSION as string | undefined,
    environment: appEnv(),
    sendDefaultPii: false,
    tracesSampleRate: 0,
    beforeSend,
  });
  enabled = true;
  return true;
}

export function captureException(error: unknown, tags: Record<string, string> = {}): void {
  if (enabled) Sentry.captureException(error, { tags });
}
