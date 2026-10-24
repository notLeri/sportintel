/// <reference types="vite/client" />

interface ImportMetaEnv {
  // Только публичные значения (FE-T0.7 §15).
  readonly VITE_SENTRY_DSN?: string;
  readonly VITE_VERSION?: string;
}
