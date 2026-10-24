// Обоснование важности приходит кодами без языка: «rules: rule:Травма(+6), top_club:(+1) · stale».
// Текст на языке интерфейса собирается здесь.
const TOKEN = /^(rule|competition|top_club|rumor|clickbait):(.*)\(([+-]\d+)\)$/;
const MODS = new Set(["priority_up", "priority_down", "stale"]);

export interface RationalePart {
  kind: "rule" | "competition" | "top_club" | "rumor" | "clickbait";
  name: string;
  points: number;
}

export function parseRationale(text: string) {
  const [main = "", ...rest] = text.split(" · ");
  const mods = rest.filter((m) => MODS.has(m));
  if (!main.startsWith("rules: "))
    return { base: null, parts: [] as RationalePart[], mods, raw: main || null };
  const body = main.slice("rules: ".length);
  if (body === "not_sports" || body === "no_signals")
    return { base: body, parts: [] as RationalePart[], mods, raw: null };
  const parts = body
    .split(", ")
    .map((x) => TOKEN.exec(x.trim()))
    .filter((m): m is RegExpExecArray => m !== null)
    .map((m) => ({
      kind: m[1] as RationalePart["kind"],
      name: m[2] ?? "",
      points: Number(m[3]),
    }));
  return { base: null, parts, mods, raw: null };
}
