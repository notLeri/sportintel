import { useQueryClient } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { devLogin, meQuery, passwordLogin, type Role } from "@/entities/user";
import { isAppError } from "@/shared/api";
import { devLoginAvailable, oidcLoginAvailable } from "@/shared/lib/env";
import { Alert, AlertDescription, BrandLogo, BrandMark, Button, Input, Label } from "@/shared/ui";

const route = getRouteApi("/login");
const ROLES: Role[] = ["researcher", "editor", "admin"];
const KNOWN_ERRORS = new Set([
  "auth.not_allowed",
  "auth.email_not_verified",
  "auth.user_inactive",
  "auth.state_mismatch",
  "auth.oidc_failed",
  "auth.oidc_disabled",
]);
// Ошибки формы пароля; прочее (сеть, 5xx) — общее «не удалось войти».
const PASSWORD_ERRORS = new Set(["auth.bad_credentials", "common.rate_limited"]);

export function LoginPage() {
  const { t } = useTranslation(["auth", "errors"]);
  const { next = "/", error } = route.useSearch();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [email, setEmail] = useState("admin@example.com");
  const [role, setRole] = useState<Role>("admin");
  const [busy, setBusy] = useState(false);
  const [login, setLogin] = useState({ email: "", password: "" });
  const [loginError, setLoginError] = useState<string | null>(null);

  async function onPasswordLogin(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setLoginError(null);
    try {
      queryClient.setQueryData(meQuery.queryKey, await passwordLogin(login.email, login.password));
      await navigate({ to: next });
    } catch (err) {
      const code = isAppError(err) ? err.code : "";
      setLoginError(PASSWORD_ERRORS.has(code) ? code : "auth.oidc_failed");
    } finally {
      setBusy(false);
    }
  }

  async function onDevLogin(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    try {
      queryClient.setQueryData(meQuery.queryKey, await devLogin(email, role));
      await navigate({ to: next });
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-dvh lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
      <LoginPoster tagline={t("auth:login.tagline")} />
      <main className="mx-auto w-full max-w-sm space-y-6 self-center px-6 py-12">
        <h1 className="font-display text-3xl font-bold">{t("auth:login.title")}</h1>
        {error ? (
          <Alert variant="destructive" role="alert">
            <AlertDescription>
              {t(`errors:${KNOWN_ERRORS.has(error) ? error : "auth.oidc_failed"}`)}
            </AlertDescription>
          </Alert>
        ) : null}
        <form onSubmit={onPasswordLogin} className="space-y-3" aria-label={t("auth:login.title")}>
          <div className="space-y-1">
            <Label htmlFor="login-email">{t("auth:login.email")}</Label>
            <Input
              id="login-email"
              type="email"
              autoComplete="username"
              required
              value={login.email}
              onChange={(e) => setLogin({ ...login, email: e.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="login-password">{t("auth:login.password")}</Label>
            <Input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              aria-describedby="login-password-hint"
              value={login.password}
              onChange={(e) => setLogin({ ...login, password: e.target.value })}
            />
            <p id="login-password-hint" className="text-muted-foreground text-xs">
              {t("auth:login.passwordHint")}
            </p>
          </div>
          {loginError ? (
            <p role="alert" className="text-destructive text-sm">
              {t(`errors:${loginError}`)}
            </p>
          ) : null}
          <Button type="submit" className="w-full" disabled={busy}>
            {t("auth:login.submit")}
          </Button>
        </form>

        {oidcLoginAvailable() ? (
          <>
            <p className="text-muted-foreground text-center text-xs uppercase">
              {t("auth:login.or")}
            </p>
            {/* Обычная ссылка, не fetch: OIDC требует полной навигации (FE-T0.18 §22). */}
            <Button asChild variant="outline" className="w-full">
              <a href={`/auth/login?${new URLSearchParams({ next })}`}>{t("auth:login.button")}</a>
            </Button>
          </>
        ) : null}

        {devLoginAvailable() ? (
          <form
            onSubmit={onDevLogin}
            className="bg-card space-y-3 rounded-lg border p-4"
            aria-label={t("auth:dev.title")}
          >
            <p className="text-muted-foreground text-sm">{t("auth:dev.title")}</p>
            <div className="space-y-1">
              <Label htmlFor="dev-email">{t("auth:dev.email")}</Label>
              <Input
                id="dev-email"
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="dev-role">{t("auth:dev.role")}</Label>
              <select
                id="dev-role"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={role}
                onChange={(e) => setRole(e.target.value as Role)}
              >
                {ROLES.map((r) => (
                  <option key={r} value={r}>
                    {t(`enums:Role.${r}`)}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" variant="outline" className="w-full" disabled={busy}>
              {t("auth:dev.submit", { role: t(`enums:Role.${role}`) })}
            </Button>
          </form>
        ) : null}
      </main>
    </div>
  );
}

/*
 * Панель входа: тёмное поле логотипа, крупный знак собирается один раз при открытии
 * (страница открывается редко — здесь уместна выразительная анимация).
 */
function LoginPoster({ tagline }: { tagline: string }) {
  return (
    <section
      aria-hidden
      className="bg-rail relative flex min-h-56 flex-col justify-between gap-8 overflow-hidden p-6 text-white lg:min-h-dvh lg:p-12"
    >
      <span
        className="pointer-events-none absolute -top-1/4 -right-1/4 size-[70%] rounded-full opacity-25 blur-3xl"
        style={{ background: "var(--brand-bright)" }}
      />
      <BrandLogo className="relative text-xl" />
      <BrandMark animated className="relative h-auto w-full max-w-sm max-lg:hidden" />
      <p className="font-display relative max-w-[22ch] text-2xl leading-tight font-bold lg:text-4xl">
        {tagline}
      </p>
    </section>
  );
}
