// Полнота локализации (FE-T5.4): ключи из кода есть в pt-BR (ошибка), en/ru в паритете с pt-BR (предупреждение),
// значения enum из openapi.json переведены в pt-BR (ошибка). Без внешних парсеров: регулярки по исходникам.
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("..", import.meta.url).pathname;
const LOCALES = join(ROOT, "src/shared/i18n/locales");
const BASE = "pt-BR";
type Tree = Record<string, unknown>;

function flat(obj: Tree, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v && typeof v === "object") for (const [kk, vv] of flat(v as Tree, key)) out.set(kk, vv);
    else out.set(key, String(v));
  }
  return out;
}

function load(locale: string): Map<string, string> {
  const out = new Map<string, string>();
  for (const f of readdirSync(join(LOCALES, locale)).filter((x) => x.endsWith(".json"))) {
    const ns = f.replace(/\.json$/, "");
    for (const [k, v] of flat(JSON.parse(readFileSync(join(LOCALES, locale, f), "utf8")) as Tree))
      out.set(`${ns}:${k}`, v);
  }
  return out;
}

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    if (statSync(p).isDirectory()) return f === "generated" ? [] : files(p);
    return /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f) ? [p] : [];
  });
}

const base = load(BASE);
const has = (key: string) =>
  base.has(key) || [...base.keys()].some((k) => k.startsWith(`${key}.`) || k.startsWith(`${key}_`));
const errors: string[] = [];
const warnings: string[] = [];

// 1. Статические ключи из кода. Пространство имён — префикс «ns:» или первое из useTranslation(...) файла.
for (const file of files(join(ROOT, "src"))) {
  const src = readFileSync(file, "utf8");
  // Пространство имён — ближайший предыдущий useTranslation(...) или аннотация «i18n-ns: <ns>» (для функций, получающих t).
  const scopes = [...src.matchAll(/useTranslation\(\s*(?:\[\s*)?"([\w-]+)"/g)].map(
    (m) => [m.index, m[1] as string] as const,
  );
  const annotated = src.match(/i18n-ns:\s*([\w-]+)/)?.[1];
  for (const m of src.matchAll(/\bt\(\s*"([\w.:-]+)"/g)) {
    const raw = m[1] as string;
    const ns =
      [...scopes].reverse().find(([i]) => i < (m.index ?? 0))?.[1] ?? annotated ?? "common";
    const key = raw.includes(":") ? raw : `${ns}:${raw}`;
    if (!has(key)) errors.push(`${file.replace(ROOT, "")}: missing ${BASE} key ${key}`);
  }
}

// 2. Паритет en/ru с pt-BR.
for (const locale of ["en", "ru"]) {
  const other = load(locale);
  for (const k of base.keys()) {
    if (!other.has(k)) warnings.push(`${locale}: missing ${k}`);
    else if (other.get(k) === "__todo") warnings.push(`${locale}: __todo ${k}`);
  }
  for (const k of other.keys())
    if (!base.has(k)) warnings.push(`${locale}: extra ${k} (not in ${BASE})`);
}

// 3. Значения enum, которые UI собирает динамически (enums:<Name>.<value>), — по openapi.json.
const api = JSON.parse(readFileSync(join(ROOT, "../openapi.json"), "utf8")) as {
  components: { schemas: Record<string, { enum?: string[] }> };
};
const ENUMS: Record<string, string> = {
  EventStatus: "EventStatus",
  Role: "Role",
  SourceTier: "",
  ReliabilityFactor: "ReliabilityFactor",
};
for (const [schema, ns] of Object.entries(ENUMS)) {
  for (const v of api.components.schemas[schema]?.enum ?? [])
    if (ns && !base.has(`enums:${ns}.${v}`)) errors.push(`enums:${ns}.${v} missing in ${BASE}`);
}
for (const group of ["Relevance", "Reliability", "RejectionReason", "ArticleState"]) {
  if (![...base.keys()].some((k) => k.startsWith(`enums:${group}.`)))
    errors.push(`enums:${group} missing in ${BASE}`);
}

for (const w of warnings) console.warn(`warning: ${w}`);
for (const e of errors) console.error(`error: ${e}`);
console.log(
  `i18n: ${base.size} keys in ${BASE}, ${errors.length} errors, ${warnings.length} warnings`,
);
process.exit(errors.length ? 1 : 0);
