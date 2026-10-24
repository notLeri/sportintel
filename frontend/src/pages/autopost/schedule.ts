// i18n-ns: admin — функции файла получают t из useTranslation("admin")
// Слоты расписания по дням в TZ пользователя (сервер отдаёт UTC) и общие мелочи вкладки.
import { isAppError } from "@/shared/api";
import { i18n } from "@/shared/i18n";

export const KEY = ["channels"] as const;
// Расписание пресетами: cron понятен не всем. Время — UTC (как у сервера).
export const PRESETS = ["*/30 * * * *", "0 * * * *", "0 9,18 * * *", "0 9 * * *"] as const;

export function errorText(e: unknown): string {
  return isAppError(e) ? (e.fieldErrors[0]?.message ?? e.title) : String(e);
}

export function scheduleLabel(t: (k: string) => string, cron: string): string {
  return (PRESETS as readonly string[]).includes(cron)
    ? t(`channels.preset.${cron}`)
    : `cron: ${cron}`;
}

export interface Slot {
  at: string; // ISO UTC
  posts: number; // сколько сообщений уйдёт в этот запуск
}

export interface Day {
  key: string; // YYYY-MM-DD в TZ пользователя
  date: Date;
  slots: Slot[];
}

export function dayKey(iso: string | Date, timeZone: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone }).format(new Date(iso));
}

/** days дней начиная с сегодняшнего; слоты вне окна не показываются. */
export function groupByDay(
  runs: string[],
  queue: { run_at: string }[],
  now: Date,
  timeZone: string,
  days = 7,
): Day[] {
  const count = new Map<string, number>();
  for (const q of queue) count.set(q.run_at, (count.get(q.run_at) ?? 0) + 1);
  const out: Day[] = [];
  for (let i = 0; i < days; i++) {
    const date = new Date(now.getTime() + i * 86_400_000);
    out.push({ key: dayKey(date, timeZone), date, slots: [] });
  }
  for (const at of runs) {
    out.find((d) => d.key === dayKey(at, timeZone))?.slots.push({ at, posts: count.get(at) ?? 0 });
  }
  return out;
}

export { fromLocalInput, toLocalInput, zoned, zonedToUtc } from "@/shared/lib/datetime";

export const time = (iso: string, timeZone: string) =>
  new Intl.DateTimeFormat(i18n.language, { hour: "2-digit", minute: "2-digit", timeZone }).format(
    new Date(iso),
  );

/** «Сегодня», «Завтра» или «пн, 12 окт.» в TZ пользователя. */
export function dayLabel(t: (k: string) => string, iso: string, timeZone: string): string {
  const now = new Date();
  const k = dayKey(iso, timeZone);
  if (k === dayKey(now, timeZone)) return t("autopost.today");
  if (k === dayKey(new Date(now.getTime() + 86_400_000), timeZone)) return t("autopost.tomorrow");
  return new Intl.DateTimeFormat(i18n.language, {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone,
  }).format(new Date(iso));
}
