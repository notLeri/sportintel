import { useTranslation } from "react-i18next";

import { type Schema, kindOf, numberError, resolve } from "@/shared/lib/jsonSchemaForm";
import { Button, Checkbox, HelpTip, Input, Textarea } from "@/shared/ui";

type Value = Record<string, unknown>;

function Field({
  name,
  schema,
  root,
  value,
  onChange,
  path,
  disabled,
}: {
  name: string;
  schema: Schema;
  root: Schema;
  value: unknown;
  onChange: (v: unknown) => void;
  path: string;
  disabled?: (path: string) => boolean;
}) {
  const { t } = useTranslation(["admin", "common", "hints", "enums"]);
  const s = resolve(schema, root);
  // Понятное имя поля и подсказка; для ключей словарей (например, «football») — имя как есть.
  const title = t(`admin:settings.fields.${name}`, { defaultValue: s.title ?? name });
  const help = t(`hints:settings.${name}`, { defaultValue: "" });
  const tip = help ? <HelpTip text={help} /> : null;
  const kind = kindOf(schema, root);
  const id = `f-${path}`;
  const off = disabled?.(path) ?? false;
  const label = (
    <span className="flex items-center">
      <label htmlFor={id} className="text-sm font-medium">
        {title}
      </label>
      {tip}
    </span>
  );
  switch (kind) {
    case "boolean":
      return (
        <div className="flex items-center gap-2">
          <Checkbox
            id={id}
            checked={Boolean(value)}
            disabled={off}
            onCheckedChange={(c) => onChange(c === true)}
          />
          {label}
        </div>
      );
    case "enum":
      return (
        <div className="space-y-1">
          {label}
          <select
            id={id}
            disabled={off}
            className="border-input h-8 w-full rounded-md border bg-transparent px-2"
            value={String(value ?? "")}
            onChange={(e) => onChange(e.target.value)}
          >
            {(s.enum ?? []).map((o) => (
              <option key={String(o)} value={String(o)}>
                {t(`enums:SettingOption.${String(o)}`, { defaultValue: String(o) })}
              </option>
            ))}
          </select>
        </div>
      );
    case "number":
    case "integer": {
      const err = numberError(value, s);
      return (
        <div className="space-y-1">
          {label}
          <Input
            id={id}
            type="number"
            disabled={off}
            step={kind === "integer" ? 1 : "any"}
            min={s.minimum}
            max={s.maximum}
            aria-invalid={Boolean(err)}
            value={value === undefined || value === null ? "" : String(value)}
            onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
          />
          {err ? <p className="text-destructive text-xs">{err}</p> : null}
        </div>
      );
    }
    case "string":
    case "text":
      return (
        <div className="space-y-1">
          {label}
          {kind === "text" ? (
            <Textarea
              id={id}
              disabled={off}
              value={String(value ?? "")}
              onChange={(e) => onChange(e.target.value)}
            />
          ) : (
            <Input
              id={id}
              disabled={off}
              value={String(value ?? "")}
              onChange={(e) => onChange(e.target.value)}
            />
          )}
        </div>
      );
    case "string[]":
      return (
        <div className="space-y-1">
          {label}
          <Textarea
            id={id}
            disabled={off}
            rows={4}
            value={((value as string[]) ?? []).join("\n")}
            onChange={(e) =>
              onChange(e.target.value.split("\n").filter((x, i, a) => x.trim() || i < a.length - 1))
            }
          />
          <p className="text-muted-foreground text-xs">{t("admin:settings.one_per_line")}</p>
        </div>
      );
    case "object":
      return (
        <fieldset className="space-y-2 rounded border p-2" aria-label={title}>
          <legend className="text-sm font-medium">
            {title}
            {tip}
          </legend>
          <Fields
            schema={s}
            root={root}
            value={(value as Value) ?? {}}
            onChange={onChange}
            path={path}
            disabled={disabled}
          />
        </fieldset>
      );
    case "dict": {
      const entries = Object.entries((value as Record<string, unknown>) ?? {});
      const set = (rows: [string, unknown][]) =>
        onChange(Object.fromEntries(rows.filter(([k]) => k)));
      return (
        <fieldset className="space-y-1" aria-label={title}>
          <legend className="text-sm font-medium">
            {title}
            {tip}
          </legend>
          {entries.map(([k, v], i) => (
            <div key={i} className="flex gap-1">
              <Input
                aria-label={`${name} ${t("admin:settings.key")} ${i + 1}`}
                value={k}
                onChange={(e) => set(entries.map((r, j) => (j === i ? [e.target.value, r[1]] : r)))}
              />
              <Input
                aria-label={`${name} ${t("admin:settings.value")} ${i + 1}`}
                value={String(v)}
                onChange={(e) => set(entries.map((r, j) => (j === i ? [r[0], e.target.value] : r)))}
              />
              <Button
                type="button"
                size="sm"
                variant="ghost"
                aria-label={t("common:remove")}
                onClick={() => set(entries.filter((_, j) => j !== i))}
              >
                ×
              </Button>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => set([...entries, ["novo", ""]])}
          >
            +
          </Button>
        </fieldset>
      );
    }
    case "object[]": {
      const items = (value as Value[]) ?? [];
      const itemSchema = resolve(s.items as Schema, root);
      return (
        <fieldset className="space-y-2" aria-label={title}>
          <legend className="text-sm font-medium">
            {title}
            {tip}
          </legend>
          {items.map((it, i) => (
            <div key={i} className="space-y-1 rounded border p-2">
              <Fields
                schema={itemSchema}
                root={root}
                value={it}
                path={`${path}.${i}`}
                disabled={disabled}
                onChange={(v) => onChange(items.map((x, j) => (j === i ? v : x)))}
              />
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => onChange(items.filter((_, j) => j !== i))}
              >
                Remover
              </Button>
            </div>
          ))}
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() =>
              onChange([
                ...items,
                Object.fromEntries(
                  Object.entries(itemSchema.properties ?? {}).map(([k, p]) => [
                    k,
                    resolve(p, root).default ?? (kindOf(p, root) === "string[]" ? [] : ""),
                  ]),
                ),
              ])
            }
          >
            +
          </Button>
        </fieldset>
      );
    }
    default:
      return <JsonField id={id} label={label} value={value} onChange={onChange} />;
  }
}

function JsonField({
  id,
  label,
  value,
  onChange,
}: {
  id: string;
  label: React.ReactNode;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  return (
    <div className="space-y-1">
      {label}
      <Textarea
        id={id}
        rows={4}
        className="font-mono text-xs"
        defaultValue={JSON.stringify(value, null, 2)}
        onBlur={(e) => {
          try {
            onChange(JSON.parse(e.target.value));
          } catch {
            /* невалидный JSON — значение не меняется */
          }
        }}
      />
    </div>
  );
}

export function Fields({
  schema,
  root,
  value,
  onChange,
  path = "",
  disabled,
}: {
  schema: Schema;
  root: Schema;
  value: Value;
  onChange: (v: Value) => void;
  path?: string;
  disabled?: (path: string) => boolean;
}) {
  return (
    <div className="space-y-3">
      {Object.entries(resolve(schema, root).properties ?? {}).map(([name, s]) => (
        <Field
          key={name}
          name={name}
          schema={s}
          root={root}
          value={value[name]}
          path={path ? `${path}.${name}` : name}
          disabled={disabled}
          onChange={(v) => onChange({ ...value, [name]: v })}
        />
      ))}
    </div>
  );
}
