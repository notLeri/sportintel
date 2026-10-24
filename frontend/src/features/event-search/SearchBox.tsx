import { getRouteApi } from "@tanstack/react-router";
import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { type EntityItem, useEntitiesByIds } from "@/entities/taxonomy";
import { useHotkey } from "@/shared/lib/hotkeys";
import { Badge, Input } from "@/shared/ui";

import { useEntitySuggestions } from "./useEntitySuggestions";

const route = getRouteApi("/");
const Q_MAX = 200;

type Option = { kind: "text" } | { kind: "entity"; e: EntityItem };

export function SearchBox({ hotkeys = true }: { hotkeys?: boolean }) {
  const { t } = useTranslation(["dashboard", "enums"]);
  const search = route.useSearch();
  const navigate = route.useNavigate();
  const set = (patch: { q?: string; entity?: string[] }) =>
    void navigate({ search: (prev) => ({ ...prev, ...patch }), replace: true });
  const entities = search.entity ?? [];
  const names = useEntitiesByIds(entities);
  const [text, setText] = useState(search.q ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const listId = useId();
  const { items } = useEntitySuggestions(text);

  useEffect(() => setText(search.q ?? ""), [search.q]);
  useHotkey(
    "/",
    (e) => {
      e.preventDefault();
      input.current?.focus();
    },
    { enabled: hotkeys },
  );

  const trimmed = text.trim().slice(0, Q_MAX);
  const options: Option[] = trimmed
    ? [{ kind: "text" }, ...items.map((e) => ({ kind: "entity" as const, e }))]
    : [];
  const choose = (o: Option | undefined) => {
    if (!o || o.kind === "text") set({ q: trimmed || undefined });
    else {
      set({ entity: [...new Set([...entities, o.e.id])] });
      setText(search.q ?? "");
    }
    setOpen(false);
  };
  const removeEntity = (id: string) => {
    const rest = entities.filter((x) => x !== id);
    set({ entity: rest.length ? rest : undefined });
  };
  const optId = (i: number) => `${listId}-opt-${i}`;
  // группировка подсказок по kind: заголовок группы — перед первой сущностью своего вида
  const groupStart = (i: number) => {
    const o = options[i];
    const prev = options[i - 1];
    return o?.kind === "entity" && (prev?.kind !== "entity" || prev.e.kind !== o.e.kind);
  };

  return (
    <div className="relative space-y-1">
      <div className="flex items-center gap-1">
        <Input
          ref={input}
          role="combobox"
          aria-expanded={open && options.length > 0}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && options.length ? optId(active) : undefined}
          aria-label={t("search_label")}
          aria-describedby={`${listId}-hint`}
          placeholder={t("search_label")}
          maxLength={Q_MAX}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setActive(0);
            setOpen(true);
          }}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setOpen(true);
              setActive((a) => Math.min(a + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setActive((a) => Math.max(a - 1, 0));
            } else if (e.key === "Enter") {
              e.preventDefault();
              choose(open ? options[active] : undefined);
            } else if (e.key === "Escape") {
              if (open) setOpen(false);
              else input.current?.blur();
            } else if (e.key === "Backspace" && !text && entities.length) {
              removeEntity(entities[entities.length - 1] ?? "");
            }
          }}
          onBlur={() => setOpen(false)}
        />
        {search.q ? (
          <button
            type="button"
            aria-label={t("clear_search")}
            className="px-1"
            onClick={() => set({ q: undefined })}
          >
            ×
          </button>
        ) : null}
      </div>
      {open && options.length ? (
        <ul
          id={listId}
          role="listbox"
          aria-label={t("suggestions")}
          className="bg-popover absolute z-20 w-full rounded-md border p-1 shadow"
        >
          {options.map((o, i) => (
            <li key={o.kind === "text" ? "text" : o.e.id}>
              {groupStart(i) && o.kind === "entity" ? (
                <div className="text-muted-foreground px-2 pt-1 text-xs">
                  {t(`entity_kind.${o.e.kind}`)}
                </div>
              ) : null}
              <div
                id={optId(i)}
                role="option"
                aria-selected={i === active}
                tabIndex={-1}
                className={
                  i === active ? "bg-accent rounded px-2 py-1 text-sm" : "px-2 py-1 text-sm"
                }
                onMouseDown={(e) => {
                  e.preventDefault(); // не терять фокус поля до выбора
                  choose(o);
                }}
                onKeyDown={() => undefined}
              >
                {o.kind === "text" ? t("search_for", { text: trimmed }) : o.e.name}
              </div>
            </li>
          ))}
        </ul>
      ) : null}
      {entities.length ? (
        <div className="flex flex-wrap gap-1">
          {entities.map((id) => {
            const e = names.data?.find((x) => x.id === id);
            const label = e?.name ?? (names.isSuccess ? t("entity_removed") : "…");
            return (
              <Badge key={id} variant="secondary" className="gap-1">
                {label}
                <button
                  type="button"
                  aria-label={t("remove", { name: label })}
                  onClick={() => removeEntity(id)}
                >
                  ×
                </button>
              </Badge>
            );
          })}
        </div>
      ) : null}
      <p id={`${listId}-hint`} className="text-muted-foreground text-xs">
        {t("search_hint")}
      </p>
    </div>
  );
}
