import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { i18n } from "@/shared/i18n";

import { server } from "./msw/server";

// jsdom сообщает navigator.language = en-US; тесты пишутся под основной язык интерфейса.
void i18n.changeLanguage("pt-BR");

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
  localStorage.clear(); // фильтры событий и черновики запоминаются — тесты не должны их делить
});
afterAll(() => server.close());

// jsdom не считает layout: виртуализированным спискам (FE-T2.26) нужен ненулевой размер контейнера.
Object.defineProperty(HTMLElement.prototype, "offsetHeight", {
  configurable: true,
  get: () => 800,
});
Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, get: () => 600 });
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver;

// Node ≥ 22 объявляет свой globalThis.localStorage (без --localstorage-file он неработоспособен)
// и перекрывает jsdom. Тестам нужен обычный in-memory Storage.
if (typeof globalThis.localStorage?.clear !== "function") {
  const data = new Map<string, string>();
  const storage = {
    get length() {
      return data.size;
    },
    clear: () => data.clear(),
    getItem: (k: string) => data.get(k) ?? null,
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (k: string) => void data.delete(k),
    setItem: (k: string, v: string) => void data.set(k, String(v)),
  };
  // Object.keys(localStorage) в draft-autosave → ключи должны быть перечисляемы.
  const proxy = new Proxy(storage, {
    ownKeys: () => [...data.keys()],
    getOwnPropertyDescriptor: (_t, k) =>
      data.has(String(k))
        ? { enumerable: true, configurable: true, value: data.get(String(k)) }
        : undefined,
  });
  Object.defineProperty(globalThis, "localStorage", { configurable: true, value: proxy });
}
