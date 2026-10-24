import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { type EventDetail, eventDetailQuery } from "@/entities/event";
import { EntityMultiSelect, useSports } from "@/entities/taxonomy";
import { isAppError } from "@/shared/api";
import { Button, Input, Label, Textarea, toast } from "@/shared/ui";

import { ConflictDiffDialog } from "./ConflictDiffDialog";
import { changedPatch, type DiffRow, diffFields, type EditValues, valuesOf } from "./diffFields";
import { useEditEvent } from "./useEditEvent";

/** Форма правки (FE-T3.5). База и версия фиксируются при входе в режим правки (§22). */
export function EditEventForm({ event, onDone }: { event: EventDetail; onDone: () => void }) {
  const { t } = useTranslation(["event", "dashboard"]);
  const qc = useQueryClient();
  const sports = useSports();
  const edit = useEditEvent(event.id);
  const [base, setBase] = useState(() => ({ values: valuesOf(event), version: event.version }));
  const [v, setV] = useState<EditValues>(base.values);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [conflict, setConflict] = useState<{ rows: DiffRow[]; version: number } | null>(null);
  const patch = changedPatch(base.values, v);
  const dirty = Object.keys(patch).length > 0;
  const invalid = !v.title.trim() || v.title.length > 300 || v.summary.length > 3000;
  const set = <K extends keyof EditValues>(k: K, value: EditValues[K]) =>
    setV((p) => ({ ...p, [k]: value }));

  const submit = (version = base.version) =>
    edit.mutate(
      { patch, version },
      {
        onSuccess: () => {
          toast.success(t("edit.saved"));
          onDone();
        },
        onError: async (err) => {
          if (isAppError(err) && err.status === 412) {
            const theirs = await qc.fetchQuery({ ...eventDetailQuery(event.id), staleTime: 0 });
            setConflict({ rows: diffFields(base.values, v, theirs), version: theirs.version });
          } else if (isAppError(err) && err.fieldErrors.length) {
            setErrors(Object.fromEntries(err.fieldErrors.map((f) => [f.field, f.message])));
          } else toast.error(isAppError(err) ? err.title : t("load_failed"));
        },
      },
    );

  return (
    // Esc и Ctrl/Cmd+Enter внутри формы — горячие клавиши правки (FE-T3.5 §7).
    // eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions
    <form
      aria-label={t("edit.title")}
      className="space-y-3 rounded-md border p-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (dirty && !invalid) submit();
      }}
      onKeyDown={(e) => {
        if (e.key === "Escape") onDone();
        if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && dirty && !invalid) submit();
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="ev-title">{t("edit.fields.title")}</Label>
        <Input
          id="ev-title"
          value={v.title}
          maxLength={300}
          aria-invalid={Boolean(errors.title) || !v.title.trim()}
          onChange={(e) => set("title", e.target.value)}
        />
        {errors.title ? <p className="text-destructive text-xs">{errors.title}</p> : null}
      </div>
      <div className="space-y-1">
        <Label htmlFor="ev-summary">{t("edit.fields.summary")}</Label>
        <Textarea
          id="ev-summary"
          rows={5}
          value={v.summary}
          maxLength={3000}
          onChange={(e) => set("summary", e.target.value)}
        />
        <p className="text-muted-foreground text-right text-xs">{v.summary.length}/3000</p>
      </div>
      <div className="space-y-1">
        <Label htmlFor="ev-sport">{t("dashboard:sport")}</Label>
        <select
          id="ev-sport"
          className="border-input h-8 w-full rounded-md border bg-transparent px-2"
          value={v.sport_id}
          onChange={(e) => set("sport_id", e.target.value)}
        >
          <option value="">{t("dashboard:unclassified")}</option>
          {(sports.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
        {errors.sport_id ? <p className="text-destructive text-xs">{errors.sport_id}</p> : null}
      </div>
      <EntityMultiSelect
        label={t("dashboard:competition")}
        kind="competition"
        values={v.competition_id ? [v.competition_id] : []}
        onChange={(ids) => set("competition_id", ids.at(-1) ?? "")}
      />
      <EntityMultiSelect
        label={t("teams")}
        kind="team"
        values={v.team_ids}
        onChange={(ids) => set("team_ids", ids)}
      />
      <EntityMultiSelect
        label={t("players")}
        kind="player"
        values={v.player_ids}
        onChange={(ids) => set("player_ids", ids)}
      />
      <div className="flex gap-2">
        <Button
          type="submit"
          size="sm"
          disabled={!dirty || invalid || edit.isPending}
          aria-keyshortcuts="Control+Enter"
        >
          {t("edit.save")}
        </Button>
        <Button type="button" size="sm" variant="ghost" aria-keyshortcuts="Escape" onClick={onDone}>
          {t("workflow.cancel")}
        </Button>
      </div>
      <ConflictDiffDialog
        rows={conflict?.rows ?? null}
        onReload={() => {
          const fresh = qc.getQueryData<EventDetail>(eventDetailQuery(event.id).queryKey);
          if (fresh) {
            setBase({ values: valuesOf(fresh), version: fresh.version });
            setV(valuesOf(fresh));
          }
          setConflict(null);
        }}
        onOverwrite={() => {
          const version = conflict?.version ?? base.version;
          setConflict(null);
          submit(version);
        }}
      />
    </form>
  );
}
