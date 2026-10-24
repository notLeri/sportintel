import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import { Button, Checkbox, HelpTip, Hint, Label, Textarea, toast } from "@/shared/ui";

import { DraftEditor } from "./DraftEditor";

interface Format {
  post_example: string;
  post_instructions: string;
  inline_links: boolean;
  include_emoji: boolean;
  include_source_link: boolean;
  max_hashtags: number;
  template_also_reported: boolean;
  auto_mode: "llm" | "template";
  [k: string]: unknown;
}
const TOGGLES = [
  "include_emoji",
  "inline_links",
  "include_source_link",
  "template_also_reported",
] as const;
const HASHTAGS_ON = 4;
const formatKey = ["settings", "drafts"] as const;

/** «Формат постов» — общий для всех постов: что включать и образец, по которому пишет ИИ.
 * Хранится в настройках drafts; править может тот, у кого есть право на настройки. */
export function PostFormat({ current }: { current?: string }) {
  const { t } = useTranslation(["event", "hints"]);
  const me = useMe();
  const [open, setOpen] = useState(false);
  if (!me.permissions.includes("settings.manage")) return null;
  return (
    <details
      className="rounded-md border p-3 text-sm"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary className="cursor-pointer font-medium">
        {t("post_format.title")}
        <HelpTip text={t("hints:post_format.title")} />
      </summary>
      {open ? <FormatForm current={current} /> : null}
    </details>
  );
}

function FormatForm({ current }: { current?: string }) {
  const { t } = useTranslation(["event", "hints"]);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: formatKey,
    queryFn: () =>
      unwrap(api.GET("/api/v1/settings/{key}", { params: { path: { key: "drafts" } } })),
  });
  const [form, setForm] = useState<Format | null>(null);
  useEffect(() => {
    if (q.data) setForm(q.data.value as Format);
  }, [q.data]);
  const save = useMutation({
    // PUT заменяет значение целиком: остальные поля drafts (эмодзи видов спорта и т. п.) — как были
    mutationFn: (value: Format) =>
      unwrap(
        api.PUT("/api/v1/settings/{key}", { params: { path: { key: "drafts" } }, body: { value } }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(t("post_format.saved"));
    },
    onError: (e) => toast.error(isAppError(e) ? e.title : t("post_format.failed")),
  });
  const set = <K extends keyof Format>(k: K, v: Format[K]) => setForm((f) => f && { ...f, [k]: v });
  const dirty = Boolean(form && q.data && JSON.stringify(form) !== JSON.stringify(q.data.value));

  return !form ? (
    <p aria-busy="true" className="pt-2">
      {t("draft_panel.loading")}
    </p>
  ) : (
    <div className="space-y-3 pt-3">
      <Toggle
        id="pf-auto-mode"
        checked={form.auto_mode === "llm"}
        label={t("post_format.auto_mode")}
        hint={t("hints:post_format.auto_mode")}
        onChange={(v) => set("auto_mode", v ? "llm" : "template")}
      />
      <fieldset className="space-y-1.5">
        <legend className="text-muted-foreground mb-1 text-xs">{t("post_format.include")}</legend>
        {TOGGLES.map((k) => (
          <Toggle
            key={k}
            id={`pf-${k}`}
            checked={form[k]}
            label={t(`post_format.${k}`)}
            hint={t(`hints:post_format.${k}`)}
            onChange={(v) => set(k, v)}
          />
        ))}
        <Toggle
          id="pf-hashtags"
          checked={form.max_hashtags > 0}
          label={t("post_format.hashtags")}
          hint={t("hints:post_format.hashtags")}
          onChange={(v) => set("max_hashtags", v ? HASHTAGS_ON : 0)}
        />
      </fieldset>
      <div className="space-y-1">
        <div className="flex items-center justify-between gap-2">
          <span className="font-medium">
            {t("post_format.example")}
            <HelpTip text={t("hints:post_format.example")} />
          </span>
          {current ? (
            <Hint text={t("hints:post_format.use_current")}>
              <Button size="sm" variant="outline" onClick={() => set("post_example", current)}>
                {t("post_format.use_current")}
              </Button>
            </Hint>
          ) : null}
        </div>
        <DraftEditor
          label={t("post_format.example")}
          value={form.post_example}
          onChange={(v) => set("post_example", v)}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="pf-instructions">
          {t("post_format.instructions")}
          <HelpTip text={t("hints:post_format.instructions")} />
        </Label>
        <Textarea
          id="pf-instructions"
          rows={2}
          maxLength={1000}
          placeholder={t("post_format.instructions_placeholder")}
          value={form.post_instructions}
          onChange={(e) => set("post_instructions", e.target.value)}
        />
      </div>
      <p className="text-muted-foreground text-xs">{t("post_format.applies")}</p>
      <Button size="sm" disabled={!dirty || save.isPending} onClick={() => save.mutate(form)}>
        {t("post_format.save")}
      </Button>
    </div>
  );
}

function Toggle({
  id,
  checked,
  label,
  hint,
  onChange,
}: {
  id: string;
  checked: boolean;
  label: string;
  hint: string;
  onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={(v) => onChange(v === true)} />
      <Label htmlFor={id} className="font-normal">
        {label}
      </Label>
      <HelpTip text={hint} />
    </div>
  );
}
