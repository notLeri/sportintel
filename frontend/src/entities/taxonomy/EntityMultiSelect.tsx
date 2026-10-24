import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useEntitiesByIds, useEntitySearch } from "./queries";
import type { EntityKind } from "./types";
import { Badge, Button, Input, Popover, PopoverContent, PopoverTrigger } from "@/shared/ui";

/** Автодополнение сущностей с чипами выбранных (Competition в фильтрах, сущности в поиске). */
export function EntityMultiSelect({
  label,
  kind,
  values,
  onChange,
}: {
  label: string;
  kind?: EntityKind;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const { t } = useTranslation("dashboard");
  const [q, setQ] = useState("");
  const found = useEntitySearch(q, kind);
  const selected = useEntitiesByIds(values);
  const name = (id: string) => selected.data?.find((e) => e.id === id)?.name ?? "…";
  return (
    <div className="space-y-1">
      <Popover>
        <PopoverTrigger asChild>
          <Button variant="outline" size="sm" aria-label={label} className="w-full justify-start">
            {label}
            {values.length ? ` (${values.length})` : ""}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 space-y-2">
          <Input
            aria-label={t("entity_search")}
            placeholder={t("entity_search")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          {q.trim().length < 2 ? (
            <p className="text-muted-foreground text-xs">{t("min_chars")}</p>
          ) : (
            <ul className="max-h-60 overflow-auto" role="listbox" aria-label={label}>
              {(found.data ?? []).map((e) => (
                <li key={e.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={values.includes(e.id)}
                    className="hover:bg-accent w-full rounded px-2 py-1 text-left text-sm"
                    onClick={() => !values.includes(e.id) && onChange([...values, e.id])}
                  >
                    {e.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </PopoverContent>
      </Popover>
      {values.length ? (
        <div className="flex flex-wrap gap-1">
          {values.map((id) => (
            <Badge key={id} variant="secondary" className="gap-1">
              {name(id)}
              <button
                type="button"
                aria-label={t("remove", { name: name(id) })}
                onClick={() => onChange(values.filter((v) => v !== id))}
              >
                ×
              </button>
            </Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}
