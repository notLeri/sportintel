/** Окружение backend: подставляется в <meta name="app-env"> при отдаче index.html. */
export function appEnv(): string {
  const meta = document.querySelector<HTMLMetaElement>('meta[name="app-env"]')?.content;
  return meta && !meta.startsWith("%") ? meta : import.meta.env.MODE;
}

/** dev-login доступен только в local/e2e (и в Vite dev-сервере). */
export function devLoginAvailable(): boolean {
  const env = appEnv();
  return import.meta.env.DEV || env === "local" || env === "e2e";
}

/** Вход через IdP (Google): backend выключает его, если OIDC_* не заданы. Vite dev — включён. */
export function oidcLoginAvailable(): boolean {
  return document.querySelector<HTMLMetaElement>('meta[name="app-oidc"]')?.content !== "off";
}
