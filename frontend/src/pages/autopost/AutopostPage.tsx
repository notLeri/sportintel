import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { ChevronLeftIcon, ChevronRightIcon, GripVerticalIcon, SendIcon, XIcon } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { type TFunction } from "i18next";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { TimeZoneSelect } from "@/features/timezone";
import { api, unwrap } from "@/shared/api";
import type { components } from "@/shared/api/generated/schema";
import { i18n } from "@/shared/i18n";
import { formatRelative, zoneLabel } from "@/shared/lib/datetime";
import { cn } from "@/shared/lib/utils";
import { Badge, Button, DateTimePicker, HelpTip, Hint, toast } from "@/shared/ui";

import { ChannelForm, type ChannelOut, Journal } from "./ChannelForm";
import { ChannelPhone } from "./ChannelPhone";
import {
  dayKey,
  dayLabel,
  errorText,
  fromLocalInput,
  groupByDay,
  KEY,
  scheduleLabel,
  time,
  toLocalInput,
  zoned,
  zonedToUtc,
} from "./schedule";

type Schedule = components["schemas"]["ChannelSchedule"];
type Planned = components["schemas"]["PlannedPost"];
type ChannelList = components["schemas"]["ChannelList"];

/** Автопостинг: переключатель, календарь ближайших публикаций и лента канала как в Telegram. */
export function AutopostPage() {
  const { t } = useTranslation(["admin", "hints", "common"]);
  const me = useMe();
  const qc = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [editing, setEditing] = useState<ChannelOut | "new" | null>(null);
  const list = useQuery({ queryKey: KEY, queryFn: () => unwrap(api.GET("/api/v1/channels")) });
  if (!me.permissions.includes("channels.manage")) return <p className="p-4">{t("forbidden")}</p>;
  const data = list.data;
  const ch = data?.items.find((c) => c.id === selected) ?? data?.items[0];

  return (
    <section className="mx-auto max-w-[1800px] space-y-4 p-4" aria-labelledby="autopost-h">
      <header className="flex flex-wrap items-center gap-2">
        <h1 id="autopost-h" className="font-display text-2xl font-bold">
          {t("common:nav.autopost")}
          <HelpTip text={t("hints:autopost.page")} />
        </h1>
        <Button size="sm" variant="outline" className="ml-auto" onClick={() => setEditing("new")}>
          {t("channels.new")}
        </Button>
      </header>
      {data && !data.token_configured ? (
        <p role="status" className="bg-warn-bg text-warn p-2 text-sm">
          {t("channels.no_token")}
        </p>
      ) : null}
      {data && data.token_configured && !data.publish_enabled ? (
        <p role="status" className="bg-warn-bg text-warn p-2 text-sm">
          {t("channels.flag_off")}
        </p>
      ) : null}
      {editing ? (
        <ChannelForm
          initial={editing === "new" ? null : editing}
          onDone={() => {
            setEditing(null);
            void qc.invalidateQueries({ queryKey: KEY });
          }}
        />
      ) : null}
      {data?.items.length === 0 && !editing ? (
        <p className="text-muted-foreground text-sm">{t("channels.empty")}</p>
      ) : null}
      {data && data.items.length > 1 ? (
        <div role="tablist" aria-label={t("autopost.channels")} className="flex flex-wrap gap-1">
          {data.items.map((c) => (
            <Button
              key={c.id}
              role="tab"
              size="sm"
              aria-selected={c.id === ch?.id}
              variant={c.id === ch?.id ? "default" : "outline"}
              onClick={() => setSelected(c.id)}
            >
              <span
                aria-hidden
                className={cn("size-2", c.active ? "bg-brand-text" : "border-current border")}
              />
              {c.name}
            </Button>
          ))}
        </div>
      ) : null}
      {ch && data ? (
        <ChannelBoard key={ch.id} ch={ch} list={data} onEdit={() => setEditing(ch)} />
      ) : null}
    </section>
  );
}

function ChannelBoard({
  ch,
  list,
  onEdit,
}: {
  ch: ChannelOut;
  list: ChannelList;
  onEdit: () => void;
}) {
  const { t } = useTranslation(["admin", "hints"]);
  const me = useMe();
  const qc = useQueryClient();
  const [journal, setJournal] = useState(false);
  const schedule = useQuery({
    queryKey: [...KEY, ch.id, "schedule"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/channels/{channel_id}/schedule", {
          params: { path: { channel_id: ch.id } },
        }),
      ),
    refetchInterval: 60_000,
  });
  const toggle = useMutation({
    mutationFn: () =>
      unwrap(
        api.PUT("/api/v1/channels/{channel_id}", {
          params: { path: { channel_id: ch.id } },
          body: { ...ch, active: !ch.active }, // лишние поля (id, version) сервер игнорирует
          headers: { "If-Match": `"${ch.version}"` },
        }),
      ),
    onSuccess: (c) => {
      toast.success(c.active ? t("autopost.turned_on") : t("autopost.turned_off"));
      void qc.invalidateQueries({ queryKey: KEY });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const check = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/channels/{channel_id}:check", {
          params: { path: { channel_id: ch.id } },
        }),
      ),
    onSuccess: (r) => {
      const v = { title: r.title, bot: r.bot_username };
      if (r.problem) toast.error(t(`channels.check_${r.problem}`, v));
      else toast.success(t("channels.check_ok", v));
    },
    onError: (e) => toast.error(t("channels.check_failed", { error: errorText(e) })),
  });
  const [confirmTest, setConfirmTest] = useState(false);
  const test = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/channels/{channel_id}:test", {
          params: { path: { channel_id: ch.id } },
        }),
      ),
    onSuccess: () => {
      setConfirmTest(false);
      toast.success(t("channels.test_ok"));
      void qc.invalidateQueries({ queryKey: [...KEY, ch.id, "feed"] });
    },
    onError: (e) => toast.error(t("channels.test_failed", { error: errorText(e) })),
  });
  const run = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/channels/{channel_id}:run", { params: { path: { channel_id: ch.id } } }),
      ),
    onSuccess: (r) => {
      toast.success(t("channels.run_done", r));
      void qc.invalidateQueries({ queryKey: KEY });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const pins = usePins(ch.id);
  const blocked = !list.token_configured || !list.publish_enabled;
  const tz = me.timezone;
  const s = schedule.data;
  const next = s?.queue[0];

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_400px] xl:grid-cols-[minmax(0,1fr)_480px] 2xl:grid-cols-[minmax(0,1fr)_600px]">
      <div className="min-w-0 space-y-5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b pb-4">
          <Hint text={t("hints:autopost.switch")}>
            <button
              type="button"
              role="switch"
              aria-checked={ch.active}
              disabled={toggle.isPending}
              onClick={() => toggle.mutate()}
              className="group flex items-center gap-3 text-left"
            >
              <span
                aria-hidden
                className={cn(
                  "border-input flex h-8 w-14 items-center rounded-full border-[1.5px] p-0.5 transition-colors",
                  ch.active ? "bg-primary border-primary" : "bg-transparent",
                )}
              >
                <span
                  className={cn(
                    "size-6 ease-out rounded-full transition-[translate,scale,background-color] duration-200 group-active:scale-95",
                    ch.active ? "bg-primary-foreground translate-x-[25px]" : "bg-input",
                  )}
                />
              </span>
              <span>
                <span className="block text-sm font-bold">{t("autopost.switch")}</span>
                <span className="text-muted-foreground block text-xs">
                  {ch.active ? t("autopost.on") : t("autopost.off")}
                </span>
              </span>
            </button>
          </Hint>
          <div className="flex flex-wrap items-center gap-1.5 text-xs">
            <Hint text={t(`hints:channels.mode_${ch.mode}`)}>
              <Badge variant="secondary">{t(`channels.mode.${ch.mode}`)}</Badge>
            </Hint>
            <Hint text={t("hints:channels.language")}>
              <Badge variant="outline">{t(`channels.lang.${ch.language}`)}</Badge>
            </Hint>
            <Hint text={t("hints:channels.cron")}>
              <Badge variant="outline">{scheduleLabel(t, ch.cron)}</Badge>
            </Hint>
            <Hint text={t("hints:channels.max_per_run")}>
              <Badge variant="outline">{t("autopost.per_run", { count: ch.max_per_run })}</Badge>
            </Hint>
          </div>
          <div className="ml-auto flex flex-wrap gap-1">
            <Hint text={t("hints:channels.check")}>
              <Button
                size="sm"
                variant="outline"
                disabled={!list.token_configured || check.isPending}
                onClick={() => check.mutate()}
              >
                {t("channels.check")}
              </Button>
            </Hint>
            <Hint text={t("hints:channels.test")}>
              <Button
                size="sm"
                variant={confirmTest ? "destructive" : "ghost"}
                disabled={!list.token_configured || test.isPending}
                onBlur={() => setConfirmTest(false)}
                onClick={() => (confirmTest ? test.mutate() : setConfirmTest(true))}
              >
                {confirmTest ? t("channels.test_confirm") : t("channels.test")}
              </Button>
            </Hint>
            <Hint text={t("hints:channels.run")}>
              <Button
                size="sm"
                variant="outline"
                disabled={blocked || run.isPending}
                onClick={() => run.mutate()}
              >
                {t("channels.run")}
              </Button>
            </Hint>
            <Button size="sm" variant="ghost" onClick={onEdit}>
              {t("channels.edit")}
            </Button>
          </div>
        </div>

        {ch.active && blocked ? (
          <p role="status" className="bg-warn-bg text-warn p-2 text-sm">
            {t("autopost.on_but_blocked")}
          </p>
        ) : null}

        <div aria-live="polite">
          <p className="text-muted-foreground text-xs font-semibold tracking-[0.08em] uppercase">
            {t("autopost.next_post")}
          </p>
          {!s ? (
            <p className="text-muted-foreground text-sm">…</p>
          ) : next ? (
            <p className="text-lg font-bold">
              <time dateTime={next.run_at}>
                {dayLabel(t, next.run_at, tz)}, {time(next.run_at, tz)}
              </time>{" "}
              <span className="text-muted-foreground text-sm font-normal">
                · {formatRelative(next.run_at)}
                {ch.active ? "" : ` · ${t("autopost.would_be")}`}
              </span>
            </p>
          ) : (
            <p className="text-sm">
              {t("autopost.nothing_queued", {
                when: s.next_runs[0] ? time(s.next_runs[0], tz) : "—",
              })}
            </p>
          )}
          {s && Object.keys(s.skipped).length ? (
            <p className="text-muted-foreground mt-1 text-xs">
              {Object.entries(s.skipped)
                .map(([why, n]) => t(`autopost.skipped.${why}`, { count: n, lang: ch.language }))
                .join(" · ")}
            </p>
          ) : null}
        </div>

        {s ? (
          <>
            <ReadyPosts
              posts={s.posts}
              timeZone={tz}
              onPin={pins.pin}
              onUnpin={pins.unpin}
              onSend={blocked ? null : pins.send}
            />
            <Calendar
              schedule={s}
              active={ch.active}
              cron={ch.cron}
              timeZone={tz}
              onPin={pins.pin}
            />
          </>
        ) : null}

        <div>
          <Button
            size="sm"
            variant="ghost"
            aria-expanded={journal}
            onClick={() => setJournal((j) => !j)}
          >
            {t("autopost.journal")}
          </Button>
          <HelpTip text={t("hints:autopost.journal")} />
          {journal ? <Journal channelId={ch.id} timeZone={tz} /> : null}
        </div>
      </div>
      <ChannelPhone ch={ch} schedule={s} timeZone={tz} />
    </div>
  );
}

const DRAG = "application/x-sportintel-event";
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const ROW_PX = 40;
const WEEKS = 5; // как CALENDAR_AHEAD на сервере (закрепить можно на 30 дней)

function usePins(channelId: string) {
  const { t } = useTranslation("admin");
  const qc = useQueryClient();
  const refresh = () => void qc.invalidateQueries({ queryKey: [...KEY, channelId, "schedule"] });
  const path = (eventId: string) => ({ path: { channel_id: channelId, event_id: eventId } });
  const pin = useMutation({
    mutationFn: ({ eventId, at }: { eventId: string; at: string }) =>
      unwrap(
        api.PUT("/api/v1/channels/{channel_id}/pins/{event_id}", {
          params: path(eventId),
          body: { publish_at: at },
        }),
      ),
    onSuccess: () => {
      toast.success(t("autopost.pinned"));
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const unpin = useMutation({
    mutationFn: (eventId: string) =>
      unwrap(
        api.DELETE("/api/v1/channels/{channel_id}/pins/{event_id}", { params: path(eventId) }),
      ),
    onSuccess: () => {
      toast.success(t("autopost.unpinned"));
      refresh();
    },
    onError: (e) => toast.error(errorText(e)),
  });
  const send = useMutation({
    mutationFn: (eventId: string) =>
      unwrap(
        api.POST("/api/v1/channels/{channel_id}/posts/{event_id}:send", { params: path(eventId) }),
      ),
    onSuccess: (r) => {
      if (r.failed) toast.error(t("autopost.send_failed"));
      else toast.success(t("autopost.sent_now"));
      void qc.invalidateQueries({ queryKey: [...KEY, channelId] });
    },
    onError: (e) => toast.error(errorText(e)),
  });
  return {
    pin: (eventId: string, at: string) => pin.mutate({ eventId, at }),
    unpin: (eventId: string) => unpin.mutate(eventId),
    send: (eventId: string) => send.mutate(eventId),
  };
}

const chipClass = (p: Planned) =>
  p.missed
    ? "bg-destructive text-white"
    : p.pinned
      ? "bg-attention text-attention-foreground"
      : "bg-ai text-white";

/** Неделя по часам: посты стоят в своё время, готовый пост перетаскивается на любое время. */
function Calendar({
  schedule,
  active,
  cron: cronExpr,
  timeZone,
  onPin,
}: {
  schedule: Schedule;
  active: boolean;
  cron: string;
  timeZone: string;
  onPin: (eventId: string, at: string) => void;
}) {
  const { t } = useTranslation(["admin", "hints"]);
  const [week, setWeek] = useState(0); // 0 — эта неделя; закрепить можно на WEEKS вперёд
  const days = useMemo(
    () =>
      groupByDay(
        schedule.next_runs,
        schedule.queue,
        new Date(Date.now() + week * 7 * 86_400_000),
        timeZone,
      ),
    [schedule, timeZone, week],
  );
  const range = new Intl.DateTimeFormat(i18n.language, {
    day: "numeric",
    month: "short",
    timeZone,
  }).formatRange(days[0]?.date ?? new Date(), days[days.length - 1]?.date ?? new Date());
  const now = zoned(new Date(), timeZone);
  const cell = (key: string, hour: number) => `${key} ${hour}`;
  const posts = useMemo(() => {
    const m = new Map<string, Planned[]>();
    for (const p of schedule.posts) {
      if (!p.run_at) continue;
      const z = zoned(p.run_at, timeZone);
      const k = cell(z.key, z.hour);
      m.set(k, [...(m.get(k) ?? []), p]);
    }
    return m;
  }, [schedule.posts, timeZone]);
  const isPast = (key: string, hour: number) =>
    key < now.key || (key === now.key && hour < now.hour);
  const cron = new Set(
    days.flatMap((d) => d.slots.map((sl) => cell(d.key, zoned(sl.at, timeZone).hour))),
  );
  // проверка каждый час (или чаще) — отметка в каждой клетке ничего не сообщает: только подпись
  const everyHour = days.every((d) =>
    HOURS.every((h) => isPast(d.key, h) || cron.has(cell(d.key, h))),
  );
  const [over, setOver] = useState<{ cell: string; minute: number } | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = Math.max(0, now.hour - 1) * ROW_PX;
    // eslint-disable-next-line react-hooks/exhaustive-deps -- только при открытии
  }, []);

  const half = (e: React.DragEvent<HTMLElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    return e.clientY - r.top > r.height / 2 ? 30 : 0;
  };

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-sm font-bold">
          {t("autopost.calendar")}
          <HelpTip text={t("hints:autopost.calendar")} />
        </h2>
        <span className="text-muted-foreground text-xs tabular-nums">
          {t("autopost.now", { time: time(new Date().toISOString(), timeZone) })}
        </span>
        <TimeZoneSelect id="autopost-tz" />
        <div className="ml-auto flex items-center gap-1 text-sm">
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            aria-label={t("autopost.week_prev")}
            disabled={week === 0}
            onClick={() => setWeek((w) => w - 1)}
          >
            <ChevronLeftIcon aria-hidden />
          </Button>
          <span aria-live="polite" className="min-w-32 text-center tabular-nums">
            {range}
          </span>
          <Button
            size="icon"
            variant="ghost"
            className="size-7"
            aria-label={t("autopost.week_next")}
            disabled={week >= WEEKS - 1}
            onClick={() => setWeek((w) => w + 1)}
          >
            <ChevronRightIcon aria-hidden />
          </Button>
          {week ? (
            <Button size="sm" variant="ghost" className="h-7" onClick={() => setWeek(0)}>
              {t("autopost.today")}
            </Button>
          ) : null}
        </div>
      </div>
      <div
        ref={scroller}
        className={cn(
          "max-h-[26rem] overflow-y-auto border",
          !active && "[&_td]:opacity-70 [&_td]:grayscale",
        )}
      >
        <table className="w-full table-fixed border-collapse text-xs">
          <thead className="bg-background sticky top-0 z-10">
            <tr>
              <th className="w-11 border-b" aria-label={t("autopost.hour")} />
              {days.map((d) => (
                <th
                  key={d.key}
                  scope="col"
                  className={cn(
                    "border-b border-l px-1 py-1 text-left font-semibold",
                    d.key === now.key && "bg-secondary text-brand-text",
                  )}
                >
                  <span className="block truncate capitalize">
                    {new Intl.DateTimeFormat(i18n.language, {
                      weekday: "short",
                      day: "numeric",
                      timeZone,
                    }).format(d.date)}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {HOURS.map((h) => (
              <tr key={h}>
                <th
                  scope="row"
                  className="text-muted-foreground border-b pr-1 text-right align-top font-normal tabular-nums"
                >
                  {String(h).padStart(2, "0")}:00
                </th>
                {days.map((d) => {
                  const k = cell(d.key, h);
                  const past = isPast(d.key, h);
                  const here = posts.get(k) ?? [];
                  return (
                    <td
                      key={k}
                      data-cell={k}
                      style={{ height: ROW_PX }}
                      className={cn(
                        "relative border-b border-l p-0.5 align-top",
                        // прошедшее время — штриховка: сюда пост не перетащить
                        past &&
                          "bg-[repeating-linear-gradient(135deg,transparent_0_6px,var(--muted)_6px_9px)]",
                        over?.cell === k && "bg-ai/15 outline-ai outline-2 -outline-offset-2",
                      )}
                      onDragOver={(e) => {
                        if (past) return;
                        e.preventDefault();
                        e.dataTransfer.dropEffect = "move";
                        setOver({ cell: k, minute: half(e) });
                      }}
                      onDragLeave={() => setOver((o) => (o?.cell === k ? null : o))}
                      onDrop={(e) => {
                        e.preventDefault();
                        setOver(null);
                        const id = e.dataTransfer.getData(DRAG);
                        if (!id) return;
                        const at = zonedToUtc(d.key, h, half(e), timeZone);
                        // в текущем часе прошедшая половина — значит «как можно скорее»
                        const soon = new Date(Date.now() + 60_000).toISOString();
                        onPin(id, at < soon ? soon : at);
                      }}
                    >
                      {!everyHour && cron.has(k) ? (
                        <span
                          aria-hidden
                          className="bg-ai/60 pointer-events-none absolute top-1 right-1 size-1.5 rounded-full"
                        />
                      ) : null}
                      {d.key === now.key && h === now.hour ? (
                        <span
                          aria-hidden
                          className="pointer-events-none absolute inset-x-0 z-[1] h-0.5 bg-red-500 before:absolute before:-top-1 before:-left-1 before:size-2.5 before:rounded-full before:bg-red-500"
                          style={{ top: `${(now.minute / 60) * 100}%` }}
                        />
                      ) : null}
                      {over?.cell === k ? (
                        <span className="text-ai pointer-events-none absolute right-0.5 bottom-0 font-bold tabular-nums">
                          {String(h).padStart(2, "0")}:{over.minute === 0 ? "00" : "30"}
                        </span>
                      ) : null}
                      {here.map((p) => (
                        <Hint key={p.event_id} text={chipHint(t, p, timeZone)}>
                          <span
                            draggable
                            onDragStart={(e) => {
                              e.dataTransfer.setData(DRAG, p.event_id);
                              e.dataTransfer.effectAllowed = "move";
                            }}
                            className={cn(
                              "mb-0.5 block cursor-grab truncate px-1 py-0.5 leading-tight active:cursor-grabbing",
                              chipClass(p),
                            )}
                          >
                            {p.run_at ? time(p.run_at, timeZone) : ""} {p.headline}
                          </span>
                        </Hint>
                      ))}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
        <span className="flex items-center gap-1">
          <span aria-hidden className="bg-ai size-3" />
          {t("autopost.legend.queued")}
        </span>
        <span className="flex items-center gap-1">
          <span aria-hidden className="bg-attention size-3" />
          {t("autopost.legend.pinned")}
        </span>
        <span className="flex items-center gap-1">
          <span aria-hidden className="bg-destructive size-3" />
          {t("autopost.legend.missed")}
        </span>
        {everyHour ? (
          <span>{t("autopost.legend.check_every", { schedule: scheduleLabel(t, cronExpr) })}</span>
        ) : (
          <span className="flex items-center gap-1">
            <span aria-hidden className="bg-ai/60 size-1.5 rounded-full" />
            {t("autopost.legend.check")}
          </span>
        )}
        <span className="flex items-center gap-1">
          <span
            aria-hidden
            className="size-3 border bg-[repeating-linear-gradient(135deg,transparent_0_3px,var(--muted-foreground)_3px_4px)] opacity-60"
          />
          {t("autopost.legend.past")}
        </span>
        <span className="flex items-center gap-1">
          <span aria-hidden className="h-0.5 w-3 bg-red-500" />
          {t("autopost.legend.now")}
        </span>
      </p>
    </div>
  );
}

function chipHint(t: TFunction<["admin", "hints"]>, p: Planned, timeZone: string): string {
  if (p.missed) return t("hints:autopost.chip_missed");
  const when = p.run_at ? `${dayLabel(t, p.run_at, timeZone)}, ${time(p.run_at, timeZone)}` : "";
  return t(p.pinned ? "hints:autopost.chip_pinned" : "hints:autopost.chip_auto", { when });
}

/** Готовые к отправке посты: перетащить на календарь или указать время с клавиатуры. */
function ReadyPosts({
  posts,
  timeZone,
  onPin,
  onUnpin,
  onSend,
}: {
  posts: Planned[];
  timeZone: string;
  onPin: (eventId: string, at: string) => void;
  onUnpin: (eventId: string) => void;
  onSend: ((eventId: string) => void) | null; // null — публикация выключена
}) {
  const { t } = useTranslation(["admin", "hints"]);
  const [sending, setSending] = useState<string | null>(null); // второе нажатие — отправка
  return (
    <div className="space-y-1">
      <h2 className="text-sm font-bold">
        {t("autopost.ready")}
        <HelpTip text={t("hints:autopost.ready")} />
      </h2>
      {posts.length === 0 ? (
        <p className="text-muted-foreground text-sm">{t("autopost.ready_empty")}</p>
      ) : (
        <ol className="max-h-56 divide-y overflow-y-auto border-y text-sm">
          {posts.map((p) => (
            <li
              key={p.event_id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(DRAG, p.event_id);
                e.dataTransfer.effectAllowed = "move";
              }}
              className="hover:bg-muted/50 flex cursor-grab items-center gap-2 py-1.5 pr-1 active:cursor-grabbing"
            >
              <GripVerticalIcon aria-hidden className="text-muted-foreground size-4 shrink-0" />
              <span aria-hidden className={cn("size-2.5 shrink-0", chipClass(p))} />
              <span className="min-w-0 flex-1">
                <Link
                  to="/events/$eventId"
                  params={{ eventId: p.event_id }}
                  draggable={false}
                  className="block truncate underline-offset-2 hover:underline"
                >
                  {p.headline}
                </Link>
                <span
                  className={cn(
                    "block text-xs",
                    p.missed ? "text-destructive" : "text-muted-foreground",
                  )}
                >
                  {p.missed
                    ? t("autopost.missed")
                    : p.run_at
                      ? t(p.pinned ? "autopost.at_pinned" : "autopost.at_auto", {
                          when: `${dayLabel(t, p.run_at, timeZone)}, ${time(p.run_at, timeZone)}`,
                        })
                      : t("autopost.later")}
                  {p.pinned && p.pinned_by
                    ? ` · ${t("autopost.pinned_by", { name: p.pinned_by })}`
                    : ""}
                </span>
              </span>
              <DateTimePicker
                label={t("autopost.pin_at", { title: p.headline })}
                value={p.pinned && p.run_at ? toLocalInput(p.run_at, timeZone) : ""}
                placeholder={t("autopost.pick_time")}
                min={toLocalInput(new Date(Date.now() + 60_000).toISOString(), timeZone)}
                today={dayKey(new Date(), timeZone)}
                zoneLabel={zoneLabel(timeZone)}
                className="h-7 w-[11.5rem] shrink-0 text-xs"
                onChange={(v) => onPin(p.event_id, fromLocalInput(v, timeZone))}
              />
              {onSend ? (
                <Hint text={t("hints:autopost.send_now")}>
                  <Button
                    size={sending === p.event_id ? "sm" : "icon"}
                    variant={sending === p.event_id ? "destructive" : "ghost"}
                    className={cn("shrink-0", sending === p.event_id ? "h-7" : "size-7")}
                    aria-label={t("autopost.send_now", { title: p.headline })}
                    onBlur={() => setSending(null)}
                    onClick={() => {
                      if (sending !== p.event_id) return setSending(p.event_id);
                      setSending(null);
                      onSend(p.event_id);
                    }}
                  >
                    <SendIcon aria-hidden />
                    {sending === p.event_id ? t("autopost.send_confirm") : null}
                  </Button>
                </Hint>
              ) : null}
              {p.pinned ? (
                <Hint text={t("hints:autopost.unpin")}>
                  <Button
                    size="icon"
                    variant="ghost"
                    className="size-7 shrink-0"
                    aria-label={t("autopost.unpin", { title: p.headline })}
                    onClick={() => onUnpin(p.event_id)}
                  >
                    <XIcon aria-hidden />
                  </Button>
                </Hint>
              ) : null}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
