import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import type { Schema } from "@/shared/lib/jsonSchemaForm";
import { Button, toast } from "@/shared/ui";

import { Fields } from "./SchemaForm";

const settingsKey = ["settings"] as const;
// ADR-004: шаги LM неактивны, пока LM не настроена.
const LLM_ONLY = new Set([
  "ai_routing.llm_model",
  "ai_routing.embedding_model",
  "ai_routing.embeddings",
]);

export function SettingsPage() {
  const { t } = useTranslation("admin");
  const me = useMe();
  const qc = useQueryClient();
  const list = useQuery({
    queryKey: settingsKey,
    queryFn: () => unwrap(api.GET("/api/v1/settings")),
  });
  const [key, setKey] = useState<string | null>(null);
  const items = list.data?.items ?? [];
  const current = items.find((i) => i.key === (key ?? items[0]?.key));
  const [value, setValue] = useState<Record<string, unknown>>({});
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (current) setValue(current.value);
    setError(null);
  }, [current]);
  const save = useMutation({
    mutationFn: (v: Record<string, unknown>) =>
      unwrap(
        api.PUT("/api/v1/settings/{key}", {
          params: { path: { key: current?.key ?? "" } },
          body: { value: v },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: settingsKey });
      // Язык интерфейса задаётся здесь (languages.ui_language): /me вернёт его всем
      if (current?.key === "languages") void qc.invalidateQueries();
      toast.success(t("settings.saved"));
    },
    onError: (e) =>
      setError(
        isAppError(e)
          ? [e.title, ...e.fieldErrors.map((f) => `${f.field}: ${f.message}`)].join(" · ")
          : t("settings.failed"),
      ),
  });
  const llmConfigured = Boolean(
    (me.system_status as { ai?: { llm?: { configured?: boolean } } } | null)?.ai?.llm?.configured,
  );
  const disabled = (path: string) =>
    current?.key === "ai_routing" &&
    !llmConfigured &&
    (LLM_ONLY.has(`ai_routing.${path}`) || false);

  return (
    <section aria-labelledby="settings-h" className="grid gap-4 md:grid-cols-[14rem_1fr]">
      <h2 id="settings-h" className="sr-only">
        {t("settings.title")}
      </h2>
      <nav aria-label={t("settings.keys")} className="space-y-1">
        {items.map((i) => (
          <button
            key={i.key}
            type="button"
            aria-current={i.key === current?.key ? "page" : undefined}
            className={`block w-full rounded px-2 py-1 text-left text-sm ${i.key === current?.key ? "bg-accent font-medium" : "hover:bg-muted"}`}
            onClick={() => setKey(i.key)}
          >
            {t(`settings.keys_names.${i.key}`, { defaultValue: i.key })}
          </button>
        ))}
      </nav>
      {current ? (
        <form
          aria-label={current.key}
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            save.mutate(value);
          }}
        >
          <p className="text-muted-foreground text-sm">
            {t(`settings.descriptions.${current.key}`, { defaultValue: "" })}
          </p>
          {current.key === "ai_routing" && !llmConfigured ? (
            <p role="status" className="bg-muted p-2 text-sm">
              {t("settings.llm_not_configured")}
            </p>
          ) : null}
          {error ? (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          ) : null}
          <Fields
            schema={current.schema as Schema}
            root={current.schema as Schema}
            value={value}
            onChange={setValue}
            disabled={disabled}
          />
          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending}>
              {t("settings.save")}
            </Button>
            <Button type="button" variant="outline" onClick={() => setValue(current.default)}>
              {t("settings.reset")}
            </Button>
          </div>
        </form>
      ) : (
        <p aria-busy="true">…</p>
      )}
    </section>
  );
}
