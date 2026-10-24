import { useSyncExternalStore } from "react";

/** Выбор темы: явная или по системе. Начальное применение — public/theme-init.js (до отрисовки). */
export type ThemePref = "light" | "dark" | "system";
export const THEME_PREFS: ThemePref[] = ["system", "light", "dark"];

const KEY = "theme";
// matchMedia может отсутствовать (старые WebView, jsdom) — тогда «система» = светлая.
const media = () => window.matchMedia?.("(prefers-color-scheme: dark)");
const listeners = new Set<() => void>();

function read(): ThemePref {
  try {
    const v = localStorage.getItem(KEY);
    return v === "light" || v === "dark" ? v : "system";
  } catch {
    return "system";
  }
}

function apply(pref: ThemePref) {
  const dark = pref === "dark" || (pref === "system" && !!media()?.matches);
  document.documentElement.classList.toggle("dark", dark);
}

/** На время переключения цвета перетекают (класс в styles.css), а не щёлкают. */
function crossfade() {
  const root = document.documentElement;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
  root.classList.add("palette-switching");
  setTimeout(() => root.classList.remove("palette-switching"), 260);
}

export function setTheme(pref: ThemePref) {
  crossfade();
  try {
    if (pref === "system") localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, pref);
  } catch {
    // ponytail: без localStorage (приватный режим) тема живёт до перезагрузки
  }
  apply(pref);
  listeners.forEach((cb) => cb());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  // Системная тема сменилась — пересчитать, если выбран режим «как в системе».
  const onSystem = () => {
    if (read() === "system") apply("system");
    cb();
  };
  const m = media();
  m?.addEventListener("change", onSystem);
  return () => {
    listeners.delete(cb);
    m?.removeEventListener("change", onSystem);
  };
}

export function useTheme(): ThemePref {
  return useSyncExternalStore(subscribe, read, () => "system");
}

/** Фактическая тема (светлая/тёмная) — для библиотек, которые сами не читают класс .dark. */
/** Палитра акцентов (см. styles.css): «Поле» — цвета логотипа, остальные — привычные нейтральные варианты. */
export type Palette = "pitch" | "ocean" | "violet" | "graphite";
export const PALETTES: Palette[] = ["pitch", "ocean", "violet", "graphite"];
const PALETTE_KEY = "palette";

function readPalette(): Palette {
  try {
    const v = localStorage.getItem(PALETTE_KEY) as Palette | null;
    return v && PALETTES.includes(v) ? v : "pitch";
  } catch {
    return "pitch";
  }
}

export function setPalette(p: Palette) {
  crossfade();
  try {
    if (p === "pitch") localStorage.removeItem(PALETTE_KEY);
    else localStorage.setItem(PALETTE_KEY, p);
  } catch {
    // ponytail: без localStorage палитра живёт до перезагрузки
  }
  document.documentElement.dataset.palette = p;
  syncFavicon(p);
  listeners.forEach((cb) => cb());
}

// ponytail: дублирует --brand-bright из styles.css — фавикон не видит CSS-переменные страницы.
const FAVICON_ACCENT: Record<Palette, string> = {
  pitch: "#4ade80",
  ocean: "#60a5fa",
  violet: "#a78bfa",
  graphite: "#e4e4e7",
};

/** Фавикон в цвет палитры: подменяет fill акцента в public/favicon.svg. */
export async function syncFavicon(p: Palette = readPalette()) {
  const link = document.querySelector<HTMLLinkElement>('link[rel="icon"]');
  if (!link) return;
  if (p === "pitch") {
    link.href = "/favicon.svg";
    return;
  }
  try {
    const svg = await (await fetch("/favicon.svg")).text();
    link.href =
      "data:image/svg+xml," + encodeURIComponent(svg.replace("#4ade80", FAVICON_ACCENT[p]));
  } catch {
    // нет сети — остаётся статичный фавикон
  }
}

export function usePalette(): Palette {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => (document.documentElement.dataset.palette as Palette | undefined) ?? readPalette(),
    () => "pitch",
  );
}

export function useResolvedTheme(): "light" | "dark" {
  useTheme(); // подписка: перерисовка при смене выбора или системной темы
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}
