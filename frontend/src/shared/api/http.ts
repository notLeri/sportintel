import createClient, { type Middleware } from "openapi-fetch";

import { AppError } from "./errors";
import type { paths } from "./generated/schema";

// --- CSRF: токен из /me (FE-T0.18); только в памяти модуля, не в localStorage ---
let csrfToken: string | null = null;
export const csrfStore = {
  get: (): string | null => csrfToken,
  set: (token: string | null): void => {
    csrfToken = token;
  },
};

// --- 401 → /login?next=<текущий путь> ---
function redirectToLogin(): void {
  const { pathname, search } = window.location;
  if (pathname === "/login") return;
  window.location.assign(`/login?next=${encodeURIComponent(pathname + search)}`);
}

let onUnauthenticated: () => void = redirectToLogin;
export function setOnUnauthenticated(handler: () => void): void {
  onUnauthenticated = handler;
}

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

export const csrfMiddleware: Middleware = {
  onRequest({ request }) {
    const token = csrfStore.get();
    if (token && !SAFE_METHODS.has(request.method)) request.headers.set("X-CSRF-Token", token);
    return request;
  },
};

export const errorMiddleware: Middleware = {
  async onResponse({ response }) {
    if (response.ok) return response;
    if (response.status === 401) onUnauthenticated();
    throw await AppError.fromResponse(response);
  },
  onError({ error }) {
    return error instanceof AppError ? error : AppError.network(error);
  },
};

export const api = createClient<paths>({
  // Абсолютный origin: относительный baseUrl не работает в тестовом окружении (Node fetch).
  baseUrl: globalThis.location?.origin ?? "",
  credentials: "same-origin",
  // Позднее связывание: fetch, подменённый после импорта (MSW, Sentry), тоже используется.
  fetch: (request: Request) => globalThis.fetch(request),
});
api.use(csrfMiddleware, errorMiddleware);

/** Для queryFn: ошибки уже брошены middleware как AppError; 204 → undefined. */
export async function unwrap<T>(p: Promise<{ data?: T; error?: unknown }>): Promise<T> {
  const { data, error } = await p;
  if (error !== undefined) throw error instanceof AppError ? error : AppError.fromProblem(error, 0);
  return data as T;
}
