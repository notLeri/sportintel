import { useEffect, useRef } from "react";

import { type DashboardSearch, FEED_FILTER_KEYS, validateDashboardSearch } from "@/shared/routing";

import { type FilterScope, useDashboardSearch } from "./useDashboardSearch";

// ponytail: в браузере (выбор пользователя): на другом устройстве фильтры свои.
const key = (userId: string) => `filters:${userId}`;
/** Какие фильтры страница показывает и меняет; остальные сохранённые она не трогает. */
const OWNS: Record<FilterScope, (k: string) => boolean> = {
  events: (k) => k !== "event" && k !== "q",
  feed: (k) => (FEED_FILTER_KEYS as readonly string[]).includes(k),
};

function pick(search: DashboardSearch, owns: (k: string) => boolean): DashboardSearch {
  return Object.fromEntries(Object.entries(search).filter(([k, v]) => v !== undefined && owns(k)));
}

function read(userId: string): DashboardSearch | null {
  try {
    const raw = localStorage.getItem(key(userId));
    return raw ? validateDashboardSearch(JSON.parse(raw) as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

/** Фильтры закреплены за пользователем и общие для «Событий» и «Ленты»: выбранное на одной
 * странице действует на другой и после выхода и входа. Восстанавливаются, только если в адресе
 * фильтров нет (ссылка с фильтрами важнее). */
export function usePersistedFilters(userId: string, scope: FilterScope = "events") {
  const { search, set } = useDashboardSearch(scope);
  const owns = OWNS[scope];
  const current = JSON.stringify(pick(search, owns));
  // Фильтры при входе: пока адрес их не сменил (восстановление в пути), сохранённое не затираем.
  const waiting = useRef<string | null>(current);

  useEffect(() => {
    if (waiting.current === current) return;
    waiting.current = null;
    // фильтры, которых на этой странице нет (статус, период у ленты), остаются как были
    const others = Object.fromEntries(Object.entries(read(userId) ?? {}).filter(([k]) => !owns(k)));
    try {
      localStorage.setItem(key(userId), JSON.stringify({ ...others, ...pick(search, owns) }));
    } catch {
      /* приватный режим: просто не запоминаем */
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- search сериализован в current
  }, [userId, current]);

  useEffect(() => {
    const saved = current === "{}" ? read(userId) : null;
    if (saved && Object.keys(pick(saved, owns)).length) set(pick(saved, owns));
    else waiting.current = null;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- только при входе на страницу
  }, [userId]);
}
