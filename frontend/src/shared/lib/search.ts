// Разбор search params без внешних библиотек (FE-T0.8 §3). Невалидное молча отбрасывается.

export const PERIODS = ["1h", "6h", "24h", "7d", "custom"] as const;
export type Period = (typeof PERIODS)[number];

/** Список из повторяющегося параметра или через запятую; пустые элементы отбрасываются. */
export function parseList(raw: unknown): string[] {
  const parts = Array.isArray(raw) ? raw : raw === undefined || raw === null ? [] : [raw];
  return parts
    .flatMap((p) => (typeof p === "string" || typeof p === "number" ? String(p).split(",") : []))
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

export function parseEnumList<T extends string>(raw: unknown, allowed: readonly T[]): T[] {
  const set = new Set<string>(allowed);
  return [...new Set(parseList(raw))].filter((v): v is T => set.has(v));
}

export function parseEnum<T extends string>(raw: unknown, allowed: readonly T[]): T | undefined {
  return typeof raw === "string" && (allowed as readonly string[]).includes(raw)
    ? (raw as T)
    : undefined;
}

const ISO_RE = /^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})?)?$/;

/** ISO 8601 дата или дата-время; иначе undefined. */
export function parseIso(raw: unknown): string | undefined {
  if (typeof raw !== "string" || !ISO_RE.test(raw)) return undefined;
  return Number.isNaN(Date.parse(raw)) ? undefined : raw;
}

export function parsePeriod(raw: unknown): Period {
  return parseEnum(raw, PERIODS) ?? "24h";
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function parseUuid(raw: unknown): string | undefined {
  return typeof raw === "string" && UUID_RE.test(raw) ? raw.toLowerCase() : undefined;
}

export function parseText(raw: unknown, maxLength = 200): string | undefined {
  if (typeof raw !== "string") return undefined;
  const s = raw.trim().slice(0, maxLength);
  return s.length > 0 ? s : undefined;
}

// --- сериализация URL: массивы через запятую, пустые значения не пишутся ---

/** Ключи, где пустой список значим: `relevance=` — «ни один уровень» (FE-T2.25 §12). */
export const KEEP_EMPTY = new Set(["relevance"]);

export function parseSearchString(searchStr: string): Record<string, unknown> {
  const params = new URLSearchParams(searchStr.startsWith("?") ? searchStr.slice(1) : searchStr);
  const out: Record<string, string | string[]> = {};
  for (const key of new Set(params.keys())) {
    const values = params.getAll(key);
    out[key] = values.length > 1 ? values : (values[0] ?? "");
  }
  return out;
}

export function stringifySearchObject(search: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    if (value === "" && KEEP_EMPTY.has(key)) {
      params.set(key, "");
      continue;
    }
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) {
      if (value.length > 0 || KEEP_EMPTY.has(key)) params.set(key, value.join(","));
    } else {
      params.set(key, String(value));
    }
  }
  // Запятая — разделитель списков: оставляем её читаемой в адресной строке.
  const s = params.toString().replace(/%2C/gi, ",");
  return s ? `?${s}` : "";
}
