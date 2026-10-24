// Даты — только через этот модуль, с TZ пользователя из /me (CONV §11).
import { i18n } from "@/shared/i18n";

import type { Period } from "./search";

export function formatDateTime(
  iso: string | null | undefined,
  timeZone: string,
  locale = i18n.language,
): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale, {
    dateStyle: "short",
    timeStyle: "short",
    timeZone,
  }).format(new Date(iso));
}

const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400],
  ["hour", 3_600],
  ["minute", 60],
];

export function formatRelative(
  iso: string | null | undefined,
  now = new Date(),
  locale = i18n.language,
): string {
  if (!iso) return "—";
  const diff = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  for (const [unit, sec] of UNITS) {
    if (Math.abs(diff) >= sec) return rtf.format(Math.round(diff / sec), unit);
  }
  return rtf.format(0, "minute");
}

const PERIOD_MS: Record<Exclude<Period, "custom">, number> = {
  "1h": 3_600_000,
  "6h": 6 * 3_600_000,
  "24h": 24 * 3_600_000,
  "7d": 7 * 24 * 3_600_000,
};

export function periodToRange(
  period: Period,
  now: Date,
  custom: { from?: string; to?: string } = {},
): { from?: string; to?: string } {
  if (period === "custom") return { from: custom.from, to: custom.to };
  return { from: new Date(now.getTime() - PERIOD_MS[period]).toISOString() };
}

/** ISO → значение <input type="datetime-local"> в TZ пользователя. */
export function isoToLocalInput(iso: string | undefined, timeZone: string): string {
  if (!iso) return "";
  const parts = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    })
      .formatToParts(new Date(iso))
      .map((p) => [p.type, p.value]),
  );
  return `${parts.year}-${parts.month}-${parts.day}T${parts.hour}:${parts.minute}`;
}

/** Локальное время пользователя (datetime-local) в TZ → ISO UTC. Пусто → undefined. */
export function localInputToIso(value: string, timeZone: string): string | undefined {
  if (!value) return undefined;
  const asUtc = new Date(`${value}:00Z`);
  // смещение TZ в этот момент: разница между «настенным» временем в TZ и UTC
  const wall = isoToLocalInput(asUtc.toISOString(), timeZone);
  const offsetMs = new Date(`${wall}:00Z`).getTime() - asUtc.getTime();
  return new Date(asUtc.getTime() - offsetMs).toISOString();
}

/** Дата и время момента в TZ пользователя: "YYYY-MM-DD" и часы/минуты. */
export function zoned(iso: string | Date, timeZone: string) {
  const p = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      timeZone,
      hourCycle: "h23",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
      .formatToParts(new Date(iso))
      .map((x) => [x.type, x.value]),
  );
  return { key: `${p.year}-${p.month}-${p.day}`, hour: Number(p.hour), minute: Number(p.minute) };
}

/** Время hh:mm дня key ("YYYY-MM-DD") в TZ пользователя → ISO UTC. */
export function zonedToUtc(key: string, hour: number, minute: number, timeZone: string): string {
  const [y = 0, m = 1, d = 1] = key.split("-").map(Number);
  const want = Date.UTC(y, m - 1, d, hour, minute);
  let t = want;
  for (let i = 0; i < 2; i++) {
    // смещение пояса в этот момент (два прохода — на случай перехода на летнее время)
    const z = zoned(new Date(t), timeZone);
    const [zy = 0, zm = 1, zd = 1] = z.key.split("-").map(Number);
    t += want - Date.UTC(zy, zm - 1, zd, z.hour, z.minute);
  }
  return new Date(t).toISOString();
}

/** Значение для <input type="datetime-local"> в TZ пользователя и обратно. */
export function toLocalInput(iso: string, timeZone: string): string {
  const z = zoned(iso, timeZone);
  return `${z.key}T${String(z.hour).padStart(2, "0")}:${String(z.minute).padStart(2, "0")}`;
}

export function fromLocalInput(value: string, timeZone: string): string {
  const [key = "", hm = "0:0"] = value.split("T");
  const [h = 0, mi = 0] = hm.split(":").map(Number);
  return zonedToUtc(key, h, mi, timeZone);
}

/** Длительность «4 ч 50 мин» / «45 с» на языке интерфейса (для «сколько ещё ждать»). */
export function formatDuration(seconds: number, locale = i18n.language): string {
  const unit = (u: "hour" | "minute" | "second", n: number) =>
    new Intl.NumberFormat(locale, { style: "unit", unit: u, unitDisplay: "short" }).format(n);
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return unit("second", s);
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if (!h) return unit("minute", m);
  return m ? `${unit("hour", h)} ${unit("minute", m)}` : unit("hour", h);
}

/** Часовой пояс устройства — из системных часов, а не по IP: VPN его не меняет. */
export function deviceTimeZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
}

/** «GMT+3» для пояса в данный момент (с учётом летнего времени). */
export function zoneOffset(timeZone: string, at = new Date()): string {
  return (
    new Intl.DateTimeFormat("en-US", { timeZone, timeZoneName: "shortOffset" })
      .formatToParts(at)
      .find((p) => p.type === "timeZoneName")?.value ?? timeZone
  ).replace("-", "−");
}

/** «Moscow (GMT+3)» — город из IANA-имени и смещение: однозначно и коротко. */
export function zoneLabel(timeZone: string): string {
  const city = (timeZone.split("/").pop() ?? timeZone).replace(/_/g, " ");
  return `${city} (${zoneOffset(timeZone)})`;
}

/** Совпадают ли пояса прямо сейчас (Europe/Kyiv и Europe/Kiev — одно и то же). */
export function sameOffset(a: string, b: string, at = new Date()): boolean {
  return zoneOffset(a, at) === zoneOffset(b, at);
}
