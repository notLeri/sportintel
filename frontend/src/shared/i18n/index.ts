import i18next, { type i18n as I18n } from "i18next";
import ICU from "i18next-icu";
import { initReactI18next } from "react-i18next";

import enAdmin from "./locales/en/admin.json";
import enAnalytics from "./locales/en/analytics.json";
import enArticles from "./locales/en/articles.json";
import enAuth from "./locales/en/auth.json";
import enCommon from "./locales/en/common.json";
import enDashboard from "./locales/en/dashboard.json";
import enEnums from "./locales/en/enums.json";
import enEvent from "./locales/en/event.json";
import enFeed from "./locales/en/feed.json";
import enHints from "./locales/en/hints.json";
import enErrors from "./locales/en/errors.json";
import ptAdmin from "./locales/pt-BR/admin.json";
import ptAnalytics from "./locales/pt-BR/analytics.json";
import ptArticles from "./locales/pt-BR/articles.json";
import ptAuth from "./locales/pt-BR/auth.json";
import ptCommon from "./locales/pt-BR/common.json";
import ptDashboard from "./locales/pt-BR/dashboard.json";
import ptEnums from "./locales/pt-BR/enums.json";
import ptEvent from "./locales/pt-BR/event.json";
import ptFeed from "./locales/pt-BR/feed.json";
import ptHints from "./locales/pt-BR/hints.json";
import ptErrors from "./locales/pt-BR/errors.json";
import ruAdmin from "./locales/ru/admin.json";
import ruAnalytics from "./locales/ru/analytics.json";
import ruArticles from "./locales/ru/articles.json";
import ruAuth from "./locales/ru/auth.json";
import ruCommon from "./locales/ru/common.json";
import ruDashboard from "./locales/ru/dashboard.json";
import ruEnums from "./locales/ru/enums.json";
import ruEvent from "./locales/ru/event.json";
import ruFeed from "./locales/ru/feed.json";
import ruHints from "./locales/ru/hints.json";
import ruErrors from "./locales/ru/errors.json";

export const LOCALES = ["pt-BR", "en", "ru"] as const;
export type Locale = (typeof LOCALES)[number];
/** Языки переключателя в UI; pt-BR остаётся в словарях (язык источников). */
export const UI_LOCALES = ["en", "ru"] as const satisfies readonly Locale[];
export const NAMESPACES = [
  "common",
  "errors",
  "enums",
  "auth",
  "articles",
  "dashboard",
  "event",
  "admin",
  "analytics",
  "feed",
  "hints",
] as const;

export const resources = {
  "pt-BR": {
    common: ptCommon,
    errors: ptErrors,
    enums: ptEnums,
    auth: ptAuth,
    articles: ptArticles,
    admin: ptAdmin,
    analytics: ptAnalytics,
    dashboard: ptDashboard,
    event: ptEvent,
    feed: ptFeed,
    hints: ptHints,
  },
  en: {
    common: enCommon,
    errors: enErrors,
    enums: enEnums,
    auth: enAuth,
    articles: enArticles,
    admin: enAdmin,
    analytics: enAnalytics,
    dashboard: enDashboard,
    event: enEvent,
    feed: enFeed,
    hints: enHints,
  },
  ru: {
    common: ruCommon,
    errors: ruErrors,
    enums: ruEnums,
    auth: ruAuth,
    articles: ruArticles,
    admin: ruAdmin,
    analytics: ruAnalytics,
    dashboard: ruDashboard,
    event: ruEvent,
    feed: ruFeed,
    hints: ruHints,
  },
} as const;

export function createI18n(lng: Locale = "ru"): I18n {
  const instance = i18next.createInstance();
  void instance
    .use(ICU)
    .use(initReactI18next)
    .init({
      lng,
      fallbackLng: "en",
      supportedLngs: [...LOCALES],
      ns: [...NAMESPACES],
      defaultNS: "common",
      resources,
      interpolation: { escapeValue: false },
      initAsync: false,
    });
  return instance;
}

export const i18n = createI18n();

export async function setLocale(locale: Locale): Promise<void> {
  await i18n.changeLanguage(locale);
  document.documentElement.lang = locale;
}
