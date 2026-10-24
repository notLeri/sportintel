import { queryOptions, type QueryClient } from "@tanstack/react-query";

import { api, csrfStore, unwrap } from "@/shared/api";
import { setLocale, type Locale } from "@/shared/i18n";

import type { Me, Role } from "./types";

export const userKeys = {
  all: ["user"] as const,
  me: () => [...userKeys.all, "me"] as const,
};

async function fetchMe(): Promise<Me> {
  const me = await unwrap(api.GET("/api/v1/me"));
  csrfStore.set(me.csrf_token);
  void setLocale(me.locale as Locale);
  return me;
}

export const meQuery = queryOptions({
  queryKey: userKeys.me(),
  queryFn: fetchMe,
  staleTime: 60_000,
  refetchInterval: 60_000, // system_status (FE-T4.14)
  retry: false, // 401 — не сбой; 5xx показывает экран ошибки с повтором
});

/** POST /auth/logout → очистка кэша. Возвращает URL выхода IdP (или null). */
export async function logout(queryClient: QueryClient): Promise<string | null> {
  const res = await unwrap(api.POST("/auth/logout"));
  csrfStore.set(null);
  queryClient.clear();
  return res.logout_url ?? null;
}

export async function devLogin(email: string, role: Role): Promise<Me> {
  const me = await unwrap(api.POST("/auth/dev-login", { body: { email, role } }));
  csrfStore.set(me.csrf_token);
  return me;
}

export async function passwordLogin(email: string, password: string): Promise<Me> {
  const me = await unwrap(api.POST("/auth/password-login", { body: { email, password } }));
  csrfStore.set(me.csrf_token);
  return me;
}
