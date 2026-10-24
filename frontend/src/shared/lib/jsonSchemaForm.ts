// Минимальная интерпретация JSON Schema из pydantic для форм настроек (FE-T4.10 §7).

export type Schema = {
  type?: string | string[];
  $ref?: string;
  anyOf?: Schema[];
  allOf?: Schema[];
  enum?: unknown[];
  const?: unknown;
  properties?: Record<string, Schema>;
  items?: Schema;
  additionalProperties?: Schema | boolean;
  minimum?: number;
  maximum?: number;
  maxLength?: number;
  title?: string;
  description?: string;
  default?: unknown;
  $defs?: Record<string, Schema>;
};

export type FieldKind =
  | "string"
  | "text"
  | "enum"
  | "number"
  | "integer"
  | "boolean"
  | "string[]"
  | "object"
  | "dict"
  | "object[]"
  | "json";

/** $ref, allOf с одним элементом и anyOf c null разворачиваются до конкретной схемы. */
export function resolve(s: Schema, root: Schema): Schema {
  if (s.$ref) {
    const name = s.$ref.split("/").pop() ?? "";
    return resolve({ ...(root.$defs?.[name] ?? {}), ...s, $ref: undefined }, root);
  }
  if (s.allOf?.length === 1) return resolve({ ...s.allOf[0], ...s, allOf: undefined }, root);
  if (s.anyOf) {
    const nonNull = s.anyOf.filter((x) => x.type !== "null");
    if (nonNull.length === 1) return resolve({ ...nonNull[0], ...s, anyOf: undefined }, root);
    if (nonNull.every((x) => x.const !== undefined))
      return { ...s, anyOf: undefined, enum: nonNull.map((x) => x.const) };
  }
  return s;
}

export function kindOf(raw: Schema, root: Schema): FieldKind {
  const s = resolve(raw, root);
  if (s.enum) return "enum";
  const type = Array.isArray(s.type) ? s.type.find((x) => x !== "null") : s.type;
  if (type === "string") return (s.maxLength ?? 0) > 200 ? "text" : "string";
  if (type === "number" || type === "integer" || type === "boolean") return type;
  if (type === "array") {
    const it = s.items ? resolve(s.items, root) : {};
    if (it.type === "string") return "string[]";
    if (it.properties) return "object[]";
    return "json";
  }
  if (type === "object" || s.properties) {
    if (s.properties) return "object";
    if (
      typeof s.additionalProperties === "object" &&
      ["string", "number", "integer"].includes(String(resolve(s.additionalProperties, root).type))
    )
      return "dict";
  }
  return "json";
}

/** Клиентская проверка числа по min/max схемы. */
export function numberError(v: unknown, s: Schema): string | null {
  if (typeof v !== "number" || Number.isNaN(v)) return "number";
  if (s.minimum !== undefined && v < s.minimum) return `≥ ${s.minimum}`;
  if (s.maximum !== undefined && v > s.maximum) return `≤ ${s.maximum}`;
  return null;
}
