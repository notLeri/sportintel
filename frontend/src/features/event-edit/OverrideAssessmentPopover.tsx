import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { type EventDetail, eventKeys } from "@/entities/event";
import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import { RELEVANCE, RELIABILITY } from "@/shared/routing";
import {
  Button,
  Label,
  Popover,
  PopoverContent,
  PopoverTrigger,
  Textarea,
  toast,
} from "@/shared/ui";

type Kind = "relevance" | "reliability";

/** «Ajustar» оценку события (FE-T4.5), только editor+. */
export function OverrideAssessmentPopover({ event, kind }: { event: EventDetail; kind: Kind }) {
  const { t } = useTranslation(["event", "enums"]);
  const me = useMe();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [level, setLevel] = useState<string>(event[kind]);
  const [reason, setReason] = useState("");
  const overridden = event.manual_overrides.includes(kind);
  const save = useMutation({
    mutationFn: (body: { level: string | null; reason: string | null }) =>
      unwrap(
        kind === "relevance"
          ? api.PUT("/api/v1/events/{event_id}/relevance", {
              params: { path: { event_id: event.id } },
              body,
              headers: { "If-Match": `"${event.version}"` },
            })
          : api.PUT("/api/v1/events/{event_id}/reliability", {
              params: { path: { event_id: event.id } },
              body,
              headers: { "If-Match": `"${event.version}"` },
            }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(eventKeys.detail(event.id), d);
      void qc.invalidateQueries({ queryKey: [...eventKeys.all, "list"] });
      setOpen(false);
      setReason("");
    },
    onError: (e) => toast.error(isAppError(e) ? e.title : t("load_failed")),
  });
  if (!me.permissions.includes("events.override_assessment")) return null;
  const levels: readonly string[] = kind === "relevance" ? RELEVANCE : RELIABILITY;
  const enumNs = kind === "relevance" ? "Relevance" : "Reliability";
  const valid = reason.trim().length >= 3 && reason.length <= 500;
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button size="sm" variant="link" className="h-auto p-0">
          {t("override.adjust")}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-72 space-y-2">
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">{t(`override.${kind}`)}</legend>
          {levels.map((l) => (
            <label key={l} className="flex items-center gap-2 text-sm">
              <input
                type="radio"
                name={`ov-${kind}`}
                value={l}
                checked={level === l}
                onChange={() => setLevel(l)}
              />
              {t(`enums:${enumNs}.${l}`)}
            </label>
          ))}
        </fieldset>
        <div className="space-y-1">
          <Label htmlFor={`ov-reason-${kind}`}>{t("override.reason")}</Label>
          <Textarea
            id={`ov-reason-${kind}`}
            value={reason}
            maxLength={500}
            onChange={(e) => setReason(e.target.value)}
          />
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={!valid || save.isPending}
            onClick={() => save.mutate({ level, reason: reason.trim() })}
          >
            {t("edit.save")}
          </Button>
          {overridden ? (
            <Button
              size="sm"
              variant="outline"
              disabled={save.isPending}
              onClick={() => save.mutate({ level: null, reason: null })}
            >
              {t("override.auto")}
            </Button>
          ) : null}
        </div>
      </PopoverContent>
    </Popover>
  );
}
