import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { EntityMultiSelect, useSports } from "@/entities/taxonomy";
import { isAppError } from "@/shared/api";
import { newIdempotencyKey } from "@/shared/lib/idempotency";
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  Input,
  Label,
  Textarea,
  toast,
} from "@/shared/ui";

import { MAX_URLS, parseUrlLines, useCreateEvent } from "./useCreateEvent";

/** «Novo evento» (FE-T3.6). Idempotency-Key живёт от открытия до успеха. */
export function CreateEventDialog({ onCreated }: { onCreated: (eventId: string) => void }) {
  const { t } = useTranslation(["articles", "event", "dashboard"]);
  const sports = useSports();
  const create = useCreateEvent();
  const [open, setOpen] = useState(false);
  const [key, setKey] = useState(newIdempotencyKey);
  const [title, setTitle] = useState("");
  const [summary, setSummary] = useState("");
  const [sport, setSport] = useState("");
  const [competition, setCompetition] = useState<string[]>([]);
  const [teams, setTeams] = useState<string[]>([]);
  const [players, setPlayers] = useState<string[]>([]);
  const [links, setLinks] = useState("");
  const [badLine, setBadLine] = useState<number | null>(null);
  const urls = parseUrlLines(links);
  const localBad = urls.findIndex((u) => u === null);
  const tooMany = urls.length > MAX_URLS;
  const invalid = !title.trim() || localBad >= 0 || tooMany;
  const reset = () => {
    setTitle("");
    setSummary("");
    setSport("");
    setCompetition([]);
    setTeams([]);
    setPlayers([]);
    setLinks("");
    setBadLine(null);
    setKey(newIdempotencyKey());
  };

  const submit = () =>
    create.mutate(
      {
        key,
        body: {
          title: title.trim(),
          summary: summary.trim() || null,
          sport_id: sport || null,
          competition_id: competition.at(-1) ?? null,
          team_ids: teams,
          player_ids: players,
          urls: urls.filter((u): u is string => u !== null),
        },
      },
      {
        onSuccess: (ev) => {
          setOpen(false);
          reset();
          onCreated(ev.id);
          toast.success(t("event:create.created"));
          if (ev.skipped_urls.length)
            toast.info(
              <div>
                {t("event:create.skipped")}
                <ul>
                  {ev.skipped_urls.map((s) => (
                    <li key={s.url}>
                      <Link to="/" search={{ event: s.event_id }}>
                        {s.url}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>,
            );
        },
        onError: (err) => {
          const f = isAppError(err)
            ? err.fieldErrors.find((e) => /^urls\[\d+\]$/.test(e.field))
            : undefined;
          if (f) setBadLine(Number(f.field.slice(5, -1)));
          else toast.error(isAppError(err) ? err.title : t("event:load_failed"));
        },
      },
    );

  const shownBad = localBad >= 0 ? localBad : badLine;
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm">{t("event:create.button")}</Button>
      </DialogTrigger>
      <DialogContent className="max-h-[90vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>{t("event:create.title")}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!invalid) submit();
          }}
        >
          <div className="space-y-1">
            <Label htmlFor="ne-title">{t("event:edit.fields.title")}</Label>
            <Input
              id="ne-title"
              required
              maxLength={300}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ne-summary">{t("event:edit.fields.summary")}</Label>
            <Textarea
              id="ne-summary"
              maxLength={3000}
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="ne-sport">{t("dashboard:sport")}</Label>
            <select
              id="ne-sport"
              className="border-input h-8 w-full rounded-md border bg-transparent px-2"
              value={sport}
              onChange={(e) => setSport(e.target.value)}
            >
              <option value="">{t("dashboard:unclassified")}</option>
              {(sports.data ?? []).map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </div>
          <EntityMultiSelect
            label={t("dashboard:competition")}
            kind="competition"
            values={competition}
            onChange={(v) => setCompetition(v.slice(-1))}
          />
          <EntityMultiSelect
            label={t("event:teams")}
            kind="team"
            values={teams}
            onChange={setTeams}
          />
          <EntityMultiSelect
            label={t("event:players")}
            kind="player"
            values={players}
            onChange={setPlayers}
          />
          <div className="space-y-1">
            <Label htmlFor="ne-links">{t("event:create.links")}</Label>
            <Textarea
              id="ne-links"
              rows={4}
              value={links}
              aria-invalid={shownBad !== null || tooMany}
              aria-describedby="ne-links-hint"
              onChange={(e) => {
                setLinks(e.target.value);
                setBadLine(null);
              }}
            />
            <p
              id="ne-links-hint"
              className={
                shownBad !== null || tooMany
                  ? "text-destructive text-xs"
                  : "text-muted-foreground text-xs"
              }
            >
              {tooMany
                ? t("event:create.too_many", { max: MAX_URLS })
                : shownBad !== null
                  ? t("event:create.bad_line", { n: shownBad + 1 })
                  : t("event:create.links_hint")}
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              {t("event:workflow.cancel")}
            </Button>
            <Button type="submit" disabled={invalid || create.isPending}>
              {t("event:create.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
