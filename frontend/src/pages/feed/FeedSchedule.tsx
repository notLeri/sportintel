import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { FeedItem, FeedPage } from "@/entities/feed";
import { useSchedulePost } from "@/features/feed-take";
import { isAppError } from "@/shared/api";
import {
  formatDateTime,
  fromLocalInput,
  toLocalInput,
  zoned,
  zoneLabel,
} from "@/shared/lib/datetime";
import { Button, DateTimePicker, Label, toast } from "@/shared/ui";

type Channel = FeedPage["channels"][number];
const STEP_MS = 30 * 60_000;

/** Ближайшая получасовая отметка не раньше чем через 15 минут. */
function defaultTime(now = Date.now()): string {
  return new Date(Math.ceil((now + 15 * 60_000) / STEP_MS) * STEP_MS).toISOString();
}

/** Канал, на языке которого пост: туда его и планируем; иначе — первый. */
function channelFor(channels: Channel[], lang: string | undefined): Channel | undefined {
  return channels.find((c) => c.language === lang) ?? channels[0];
}

/** Выбор канала и времени: «Запланировать» утверждает пост и ставит его в календарь канала. */
export function FeedSchedule({
  item,
  channels,
  timeZone,
  onDone,
}: {
  item: FeedItem;
  channels: Channel[];
  timeZone: string;
  onDone: () => void;
}) {
  const { t } = useTranslation(["feed", "event", "hints"]);
  const schedule = useSchedulePost();
  const [channelId, setChannelId] = useState(channelFor(channels, item.draft?.lang)?.id ?? "");
  const [at, setAt] = useState(() => toLocalInput(defaultTime(), timeZone));
  const [error, setError] = useState<string | null>(null);
  const ch = channels.find((c) => c.id === channelId);

  const submit = () => {
    if (!ch) return;
    setError(null);
    const publishAt = fromLocalInput(at, timeZone);
    schedule.mutate(
      { eventId: item.event.id, version: item.event.version, channelId: ch.id, publishAt },
      {
        onSuccess: () => {
          toast.success(
            t("scheduled", { time: formatDateTime(publishAt, timeZone), channel: ch.name }),
          );
          onDone();
        },
        onError: (e) => {
          const f = isAppError(e) ? e.fieldErrors[0] : undefined;
          setError(
            f?.field === "channel_id"
              ? t(`event:draft_panel.channel_blocked.${f.code}`, {
                  channel: `«${ch.name}»`,
                  channel_lang: ch.language,
                  post_lang: item.draft?.lang ?? "—",
                })
              : isAppError(e) && e.status === 412
                ? t("changed")
                : (f?.message ?? (isAppError(e) ? e.title : t("schedule_failed"))),
          );
        },
      },
    );
  };

  return (
    <form
      aria-label={t("schedule")}
      className="bg-muted/40 space-y-2 rounded-md border p-3 text-sm"
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <div className="grid gap-2 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor={`fs-ch-${item.event.id}`}>{t("channel")}</Label>
          <select
            id={`fs-ch-${item.event.id}`}
            className="border-input h-8 w-full rounded-md border bg-transparent px-2"
            value={channelId}
            onChange={(e) => setChannelId(e.target.value)}
          >
            {channels.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name} · {c.language}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor={`fs-at-${item.event.id}`}>
            {t("schedule_at", { tz: zoneLabel(timeZone) })}
          </Label>
          <DateTimePicker
            id={`fs-at-${item.event.id}`}
            label={t("schedule_at", { tz: zoneLabel(timeZone) })}
            value={at}
            onChange={setAt}
            min={toLocalInput(new Date().toISOString(), timeZone)}
            today={zoned(new Date(), timeZone).key}
            zoneLabel={zoneLabel(timeZone)}
            className="w-full"
          />
        </div>
      </div>
      {ch && !ch.active ? <p className="text-warn text-xs">{t("channel_off")}</p> : null}
      <p className="text-muted-foreground text-xs">{t("schedule_note")}</p>
      {error ? (
        <p role="alert" className="text-destructive text-xs">
          {error}
        </p>
      ) : null}
      <div className="flex gap-2">
        <Button type="submit" size="sm" disabled={!ch || !at || schedule.isPending}>
          {t("schedule_confirm", {
            time: at ? formatDateTime(fromLocalInput(at, timeZone), timeZone) : "",
          })}
        </Button>
        <Button type="button" size="sm" variant="ghost" onClick={onDone}>
          {t("cancel")}
        </Button>
      </div>
    </form>
  );
}
