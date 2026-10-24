import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useSourcesBrief } from "@/entities/source";
import { useSports } from "@/entities/taxonomy";
import { api, isAppError, unwrap } from "@/shared/api";
import type { components } from "@/shared/api/generated/schema";
import { formatDateTime } from "@/shared/lib/datetime";
import { regionName } from "@/shared/lib/region";
import { Button, Checkbox, HelpTip, Input, Label, toast } from "@/shared/ui";

import { errorText, KEY, PRESETS } from "./schedule";

type ChannelIn = components["schemas"]["ChannelIn"];
export type ChannelOut = components["schemas"]["ChannelOut"];

const LEVELS = ["HIGH", "MEDIUM", "LOW"] as const;
const TIERS = ["OFFICIAL", "A", "B", "C"] as const;
const EMPTY: ChannelIn = {
  name: "",
  tg_chat_id: "",
  language: "en",
  mode: "approval",
  cron: "0 * * * *",
  format: "single",
  max_per_run: 3,
  min_relevance: "HIGH",
  min_trust: "MEDIUM",
  min_tier: null,
  regions: [],
  sports: [],
  source_allow: [],
  source_deny: [],
  active: false, // включается переключателем «Автопостинг» после проверки
};

export function Journal({ channelId, timeZone }: { channelId: string; timeZone: string }) {
  const { t } = useTranslation("admin");
  const q = useQuery({
    queryKey: [...KEY, channelId, "publications"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/channels/{channel_id}/publications", {
          params: { path: { channel_id: channelId } },
        }),
      ),
  });
  if (!q.data) return null;
  if (!q.data.items.length)
    return <p className="text-muted-foreground">{t("channels.journal_empty")}</p>;
  return (
    <table className="w-full text-xs">
      <tbody>
        {q.data.items.map((p) => (
          <tr key={p.id} className="border-t">
            <td className="py-1">{formatDateTime(p.created_at, timeZone)}</td>
            <td>
              <a href={`/?event=${p.event_id}`} className="underline">
                {t("channels.open_event")}
              </a>
            </td>
            <td>{t(`channels.pub_status.${p.status}`)}</td>
            <td className="text-destructive">{p.error ?? ""}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function ChannelForm({
  initial,
  onDone,
}: {
  initial: ChannelOut | null;
  onDone: () => void;
}) {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const sports = useSports();
  const sources = useSourcesBrief();
  const [f, setF] = useState<ChannelIn>(initial ? { ...EMPTY, ...initial } : EMPTY);
  const [customCron, setCustomCron] = useState(
    !(PRESETS as readonly string[]).includes(f.cron ?? ""),
  );
  const set = <K extends keyof ChannelIn>(k: K, v: ChannelIn[K]) => setF((x) => ({ ...x, [k]: v }));
  const save = useMutation({
    mutationFn: () =>
      initial
        ? unwrap(
            api.PUT("/api/v1/channels/{channel_id}", {
              params: { path: { channel_id: initial.id } },
              body: f,
              headers: { "If-Match": `"${initial.version}"` },
            }),
          )
        : unwrap(api.POST("/api/v1/channels", { body: f })),
    onSuccess: () => {
      toast.success(t("channels.saved"));
      onDone();
    },
  });
  const err = (field: string) =>
    isAppError(save.error)
      ? save.error.fieldErrors.find((x) => x.field === field)?.message
      : undefined;
  const regions = [...new Set((sources.data ?? []).map((s) => s.region).filter(Boolean))].sort();
  const toggle = <T,>(list: T[] | undefined, v: T) =>
    (list ?? []).includes(v) ? (list ?? []).filter((x) => x !== v) : [...(list ?? []), v];

  const row = (label: string, hint: string, control: React.ReactNode, error?: string) => (
    <div className="space-y-1">
      <div className="flex items-center">
        <span className="text-sm font-medium">{label}</span>
        <HelpTip text={hint} />
      </div>
      {control}
      {error ? <p className="text-destructive text-xs">{error}</p> : null}
    </div>
  );
  const select = <K extends keyof ChannelIn>(
    k: K,
    options: readonly string[],
    label: (o: string) => string,
  ) => (
    <select
      aria-label={t(`channels.field.${String(k)}`)}
      className="border-input h-8 w-full rounded-md border bg-transparent px-2"
      value={String(f[k] ?? "")}
      onChange={(e) => set(k, (e.target.value || null) as ChannelIn[K])}
    >
      {options.map((o) => (
        <option key={o} value={o}>
          {label(o)}
        </option>
      ))}
    </select>
  );

  return (
    <form
      aria-label={t("channels.form")}
      className="grid gap-3 rounded border p-3 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        save.mutate();
      }}
    >
      {row(
        t("channels.field.name"),
        t("hints:channels.name"),
        <Input
          aria-label={t("channels.field.name")}
          value={f.name}
          onChange={(e) => set("name", e.target.value)}
        />,
        err("name"),
      )}
      {row(
        t("channels.field.tg_chat_id"),
        t("hints:channels.tg_chat_id"),
        <Input
          aria-label={t("channels.field.tg_chat_id")}
          placeholder="-1001234567890"
          value={f.tg_chat_id}
          onChange={(e) => set("tg_chat_id", e.target.value.trim())}
        />,
        err("tg_chat_id"),
      )}
      {row(
        t("channels.field.language"),
        t("hints:channels.language"),
        select("language", ["ru", "en", "pt-BR"], (o) => t(`channels.lang.${o}`)),
      )}
      {row(
        t("channels.field.mode"),
        t(`hints:channels.mode_${f.mode ?? "approval"}`),
        select("mode", ["approval", "auto"], (o) => t(`channels.mode.${o}`)),
      )}
      {row(
        t("channels.field.cron"),
        t("hints:channels.cron"),
        <div className="space-y-1">
          <select
            aria-label={t("channels.field.cron")}
            className="border-input h-8 w-full rounded-md border bg-transparent px-2"
            value={customCron ? "custom" : f.cron}
            onChange={(e) => {
              const v = e.target.value;
              setCustomCron(v === "custom");
              if (v !== "custom") set("cron", v);
            }}
          >
            {PRESETS.map((p) => (
              <option key={p} value={p}>
                {t(`channels.preset.${p}`)}
              </option>
            ))}
            <option value="custom">{t("channels.preset.custom")}</option>
          </select>
          {customCron ? (
            <Input aria-label="cron" value={f.cron} onChange={(e) => set("cron", e.target.value)} />
          ) : null}
        </div>,
        err("cron"),
      )}
      {row(
        t("channels.field.format"),
        t("hints:channels.format"),
        select("format", ["single", "digest"], (o) => t(`channels.format.${o}`)),
      )}
      {row(
        t("channels.field.max_per_run"),
        t("hints:channels.max_per_run"),
        <Input
          type="number"
          min={1}
          max={20}
          aria-label={t("channels.field.max_per_run")}
          value={f.max_per_run}
          onChange={(e) => set("max_per_run", Number(e.target.value))}
        />,
      )}
      {row(
        t("channels.field.min_relevance"),
        t("hints:channels.min_relevance"),
        select("min_relevance", LEVELS, (o) => t(`enums:Relevance.${o}`)),
      )}
      {f.mode === "auto"
        ? row(
            t("channels.field.min_trust"),
            t("hints:channels.min_trust"),
            select("min_trust", LEVELS, (o) => t(`enums:Reliability.${o}`)),
          )
        : null}
      {row(
        t("channels.field.min_tier"),
        t("hints:channels.min_tier"),
        select("min_tier", ["", ...TIERS], (o) =>
          o ? t(`enums:SourceTier.${o}`) : t("channels.any"),
        ),
      )}
      <Checks
        label={t("channels.field.regions")}
        hint={t("hints:channels.regions")}
        options={regions.map((r) => [r, regionName(r)] as const)}
        values={f.regions ?? []}
        onToggle={(v) => set("regions", toggle(f.regions, v))}
      />
      <Checks
        label={t("channels.field.sports")}
        hint={t("hints:channels.sports")}
        options={(sports.data ?? []).map((s) => [s.id, s.name] as const)}
        values={f.sports ?? []}
        onToggle={(v) => set("sports", toggle(f.sports, v))}
      />
      <Checks
        label={t("channels.field.source_allow")}
        hint={t("hints:channels.source_allow")}
        options={(sources.data ?? []).map((s) => [s.id, s.name] as const)}
        values={f.source_allow ?? []}
        onToggle={(v) => set("source_allow", toggle(f.source_allow, v))}
      />
      <Checks
        label={t("channels.field.source_deny")}
        hint={t("hints:channels.source_deny")}
        options={(sources.data ?? []).map((s) => [s.id, s.name] as const)}
        values={f.source_deny ?? []}
        onToggle={(v) => set("source_deny", toggle(f.source_deny, v))}
      />
      <div className="flex gap-2 md:col-span-2">
        <Button type="submit" disabled={save.isPending}>
          {t("channels.save")}
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          {t("channels.cancel")}
        </Button>
        {save.isError && !err("name") && !err("tg_chat_id") && !err("cron") ? (
          <p className="text-destructive text-sm">{errorText(save.error)}</p>
        ) : null}
      </div>
    </form>
  );
}

function Checks({
  label,
  hint,
  options,
  values,
  onToggle,
}: {
  label: string;
  hint: string;
  options: readonly (readonly [string, string])[];
  values: string[];
  onToggle: (v: string) => void;
}) {
  const { t } = useTranslation("admin");
  return (
    <fieldset className="space-y-1" aria-label={label}>
      <legend className="text-sm font-medium">
        {label}
        <HelpTip text={hint} />
      </legend>
      {options.length === 0 ? <p className="text-muted-foreground text-xs">—</p> : null}
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        {options.map(([v, name]) => (
          <div key={v} className="flex items-center gap-1">
            <Checkbox
              id={`${label}-${v}`}
              checked={values.includes(v)}
              onCheckedChange={() => onToggle(v)}
            />
            <Label htmlFor={`${label}-${v}`} className="font-normal">
              {name}
            </Label>
          </div>
        ))}
      </div>
      {values.length === 0 ? (
        <p className="text-muted-foreground text-xs">{t("channels.all")}</p>
      ) : null}
    </fieldset>
  );
}
