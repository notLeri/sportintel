import { i18n } from "@/shared/i18n";

/** ZZ — международный источник (OfficeHolidays, англоязычные каналы): не страна. */
const WORLD = { ru: "Весь мир", en: "Worldwide", "pt-BR": "Mundo" } as Record<string, string>;

/** ISO 3166-1 → название страны на языке UI (браузер знает все страны, словарь не нужен). */
export function regionName(code: string, locale = i18n.language): string {
  if (code === "ZZ") return WORLD[locale] ?? WORLD.en ?? code;
  try {
    return new Intl.DisplayNames([locale], { type: "region" }).of(code) ?? code;
  } catch {
    return code;
  }
}

/** Язык другой, чем у интерфейса: pt-BR при ru → да; en при en → нет. */
export const isForeign = (code: string, locale = i18n.language): boolean =>
  code.split("-")[0] !== locale.split("-")[0];

/** pt-BR → «португальский» на языке UI. */
export function languageName(code: string, locale = i18n.language): string {
  try {
    return (
      new Intl.DisplayNames([locale], { type: "language" }).of(code.split("-")[0] ?? code) ?? code
    );
  } catch {
    return code;
  }
}
