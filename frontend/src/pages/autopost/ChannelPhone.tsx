import { useQuery } from "@tanstack/react-query";
import { ClockIcon, EyeIcon, FileIcon, PlayIcon, RefreshCwIcon } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { useTranslation } from "react-i18next";

import { TG_CHAT_BG, TelegramBubble } from "@/entities/draft";
import { api, unwrap } from "@/shared/api";
import type { components } from "@/shared/api/generated/schema";
import { i18n } from "@/shared/i18n";
import { cn } from "@/shared/lib/utils";
import { HelpTip } from "@/shared/ui";

import type { ChannelOut } from "./ChannelForm";
import { dayKey, dayLabel, KEY, time } from "./schedule";

type Schedule = components["schemas"]["ChannelSchedule"];
type Post = components["schemas"]["ChannelPost"];

const BLUE = "text-[#3390ec] dark:text-[#6ab3f3]";

/** «20.8K» → 20800: для формы слова «подписчиков». */
function approx(n: string): number {
  const v = parseFloat(n.replace(",", "."));
  return Math.round(v * (/K/i.test(n) ? 1e3 : /M/i.test(n) ? 1e6 : 1));
}

/** Пилюля посреди чата: дата, «Запланировано», состояние. */
function Pill({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p
      className={cn(
        "mx-auto w-fit rounded-full bg-black/25 px-2.5 py-0.5 text-center text-[13px] font-medium text-white dark:bg-white/10",
        className,
      )}
    >
      {children}
    </p>
  );
}

/** Канал глазами подписчика: как в Telegram — шапка, обои, посты по дням, внизу запланированное. */
export function ChannelPhone({
  ch,
  schedule,
  timeZone,
}: {
  ch: ChannelOut;
  schedule: Schedule | undefined;
  timeZone: string;
}) {
  const { t } = useTranslation(["admin", "hints"]);
  const feed = useQuery({
    queryKey: [...KEY, ch.id, "feed"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/channels/{channel_id}/feed", { params: { path: { channel_id: ch.id } } }),
      ),
    staleTime: 60_000,
    retry: 1,
  });
  const f = feed.data;
  const journal = useQuery({
    queryKey: [...KEY, ch.id, "publications"],
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/channels/{channel_id}/publications", {
          params: { path: { channel_id: ch.id } },
        }),
      ),
    enabled: f?.live === false,
  });
  const posts: Post[] = useMemo(() => {
    if (f?.live) return f.items;
    // дайджест пишется в журнал на каждое событие — одно сообщение показываем один раз
    const seen = new Set<string>();
    return (journal.data?.items ?? [])
      .filter((p) => p.status === "sent" && !seen.has(p.body_tg_html) && seen.add(p.body_tg_html))
      .reverse()
      .map((p) => ({
        url: "",
        html: p.body_tg_html,
        published_at: p.created_at,
        edited: false,
        views: null,
        author: null,
        forwarded_from: null,
        photos: [],
        video_thumb: null,
        sticker: null,
        unsupported: false,
        reactions: [],
        link_preview: null,
        document: null,
      }));
  }, [f, journal.data]);
  const scroller = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scroller.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [posts.length, schedule?.queue.length]);

  const subtitle = f?.live
    ? f.subscribers
      ? t("autopost.phone.subscribers", { n: f.subscribers, count: approx(f.subscribers) })
      : t("autopost.phone.live")
    : f?.reason === "unavailable"
      ? t("autopost.phone.unavailable")
      : f
        ? t("autopost.phone.journal")
        : "";
  const title = f?.title || ch.name;

  return (
    <aside
      aria-label={t("autopost.phone.label")}
      className="flex h-[calc(100dvh-6rem)] max-h-[64rem] min-h-[30rem] flex-col overflow-hidden rounded-xl border shadow-sm lg:sticky lg:top-4"
    >
      <div className="flex items-center gap-3 border-b bg-white px-4 py-2 text-black dark:border-black/40 dark:bg-[#17212b] dark:text-white">
        {f?.avatar_url ? (
          <img src={f.avatar_url} alt="" className="size-10 shrink-0 rounded-full object-cover" />
        ) : (
          <span
            aria-hidden
            className="flex size-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-b from-[#72d5fd] to-[#2a9ef1] text-lg font-semibold text-white"
          >
            {ch.name.slice(0, 1).toUpperCase()}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px] leading-5 font-semibold">
            {f?.username ? (
              <a
                href={`https://t.me/${f.username}`}
                target="_blank"
                rel="noreferrer"
                className="hover:underline"
              >
                {title}
              </a>
            ) : (
              title
            )}
          </p>
          <p className="truncate text-[13px] leading-4 text-[#707579] dark:text-[#7f91a4]">
            {subtitle}
          </p>
        </div>
        {f?.username ? (
          <a
            href={`https://t.me/${f.username}`}
            target="_blank"
            rel="noreferrer"
            className={cn("hidden text-[13px] hover:underline sm:block", BLUE)}
          >
            @{f.username}
          </a>
        ) : null}
        <HelpTip text={t("hints:autopost.phone")} />
      </div>

      <div
        ref={scroller}
        className={cn("flex-1 space-y-2 overflow-y-auto py-3 pr-3 pl-5", TG_CHAT_BG)}
      >
        {feed.isPending ? <Pill>…</Pill> : null}
        {feed.isError ? (
          <div role="alert" className="space-y-2 pt-6 text-center">
            <Pill>{t("autopost.phone.error")}</Pill>
            <button
              type="button"
              onClick={() => void feed.refetch()}
              className="mx-auto flex items-center gap-1.5 rounded-full bg-white px-3 py-1 text-[13px] font-medium text-[#3390ec] shadow dark:bg-[#182533] dark:text-[#6ab3f3]"
            >
              <RefreshCwIcon aria-hidden className="size-3.5" />
              {t("autopost.phone.retry")}
            </button>
          </div>
        ) : null}
        {f && posts.length === 0 && !journal.isPending ? (
          <Pill className="mt-6">{t("autopost.phone.empty")}</Pill>
        ) : null}
        {posts.map((p, i) => {
          const day = p.published_at ? dayKey(p.published_at, timeZone) : "";
          const prev = posts[i - 1]?.published_at;
          const newDay = day && (!prev || dayKey(prev, timeZone) !== day);
          return (
            <div key={p.url || `${p.published_at}-${i}`} className="space-y-2">
              {newDay && p.published_at ? (
                <Pill className="sticky top-0 z-10">{dateLabel(t, p.published_at, timeZone)}</Pill>
              ) : null}
              <Message post={p} timeZone={timeZone} />
            </div>
          );
        })}
        {schedule && schedule.queue.length ? (
          <>
            <Pill className="mt-4 flex items-center gap-1">
              <ClockIcon aria-hidden className="size-3.5" />
              {ch.active ? t("autopost.phone.scheduled") : t("autopost.phone.paused")}
            </Pill>
            {schedule.queue.map((q, i) => (
              <TelegramBubble
                key={`${q.run_at}-${i}`}
                tgHtml={q.body_tg_html}
                imageUrl={null}
                channelName=""
                className="max-w-[min(100%,30rem)] opacity-80 [&>div]:outline-2 [&>div]:outline-[#3390ec] [&>div]:outline-dashed"
                footer={
                  <span className="flex items-center gap-1">
                    <ClockIcon aria-hidden className="size-3" />
                    {dayLabel(t, q.run_at, timeZone)}, {time(q.run_at, timeZone)}
                  </span>
                }
              />
            ))}
          </>
        ) : null}
      </div>

      {/* как у подписчика: внизу канала — кнопка звука; здесь только для узнаваемости */}
      <div
        aria-hidden
        className="border-t bg-white py-3 text-center text-[15px] font-medium text-[#3390ec] dark:border-black/40 dark:bg-[#17212b] dark:text-[#6ab3f3]"
      >
        {t("autopost.phone.mute")}
      </div>
    </aside>
  );
}

function dateLabel(t: (k: string) => string, iso: string, timeZone: string): string {
  if (dayKey(iso, timeZone) === dayKey(new Date(), timeZone)) return t("autopost.today");
  return new Intl.DateTimeFormat(i18n.language, { day: "numeric", month: "long", timeZone }).format(
    new Date(iso),
  );
}

/** Сообщение канала с t.me: медиа, текст с разметкой, превью ссылки, реакции, просмотры. */
function Message({ post: p, timeZone }: { post: Post; timeZone: string }) {
  const { t } = useTranslation("admin");
  const footer = (
    <>
      {p.views ? (
        <>
          <EyeIcon aria-hidden className="size-3.5" />
          <span className="sr-only">{t("autopost.phone.views")}</span>
          {p.views}
        </>
      ) : null}
      {p.author ? <span className="ml-1 truncate">{p.author},</span> : null}
      {p.edited ? <span className="ml-1">{t("autopost.phone.edited")}</span> : null}
      {p.published_at ? (
        p.url ? (
          <a href={p.url} target="_blank" rel="noreferrer" className="ml-1 hover:underline">
            {time(p.published_at, timeZone)}
          </a>
        ) : (
          <span className="ml-1">{time(p.published_at, timeZone)}</span>
        )
      ) : null}
    </>
  );

  if (p.sticker && !p.html) {
    // стикер в Telegram — без пузыря, время на полупрозрачной подложке
    return (
      <div className="relative w-40">
        <img src={p.sticker} alt={t("autopost.phone.sticker")} loading="lazy" className="w-40" />
        <span className="absolute right-0 bottom-0 flex items-center gap-1 rounded-full bg-black/35 px-2 py-0.5 text-xs text-white">
          {footer}
        </span>
      </div>
    );
  }

  const media = p.video_thumb ? (
    <a href={p.url} target="_blank" rel="noreferrer" className="relative block">
      <img
        src={p.video_thumb}
        alt=""
        loading="lazy"
        className="max-h-[28rem] w-full object-cover"
      />
      <span className="absolute inset-0 m-auto flex size-12 items-center justify-center rounded-full bg-black/45 text-white">
        <PlayIcon aria-hidden className="size-6 fill-current" />
        <span className="sr-only">{t("autopost.phone.video")}</span>
      </span>
    </a>
  ) : p.document ? (
    <div className="flex items-center gap-3 px-3 pt-2">
      <span className="flex size-11 shrink-0 items-center justify-center rounded-full bg-[#3390ec] text-white">
        <FileIcon aria-hidden className="size-5" />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-medium">{p.document.title}</span>
        <span className="block text-xs text-[#a0acb6]">{p.document.extra}</span>
      </span>
    </div>
  ) : p.unsupported ? (
    <a
      href={p.url}
      target="_blank"
      rel="noreferrer"
      className={cn("block px-3 pt-2 text-sm italic hover:underline", BLUE)}
    >
      {t("autopost.phone.open_in_telegram")}
    </a>
  ) : undefined;

  const lp = p.link_preview;
  const extra = (
    <>
      {lp && (lp.title || lp.description) ? (
        <a
          href={lp.url ?? p.url}
          target="_blank"
          rel="noreferrer"
          className="mt-1.5 block overflow-hidden rounded border-l-[3px] border-[#3390ec] bg-[#3390ec]/10 px-2 py-1 text-sm"
        >
          {lp.site ? <span className={cn("block font-semibold", BLUE)}>{lp.site}</span> : null}
          {lp.title ? <span className="block font-semibold">{lp.title}</span> : null}
          {lp.description ? <span className="line-clamp-3 block">{lp.description}</span> : null}
          {lp.image ? <img src={lp.image} alt="" loading="lazy" className="mt-1 rounded" /> : null}
        </a>
      ) : null}
      {p.reactions.length ? (
        <ul className="mt-1.5 flex flex-wrap gap-1" aria-label={t("autopost.phone.reactions")}>
          {p.reactions.map((r) => (
            <li
              key={r.emoji}
              className="rounded-full bg-[#3390ec]/15 px-2 py-0.5 text-[13px] font-medium text-[#3390ec] dark:text-[#6ab3f3]"
            >
              {r.emoji} {r.count}
            </li>
          ))}
        </ul>
      ) : null}
    </>
  );

  return (
    <TelegramBubble
      tgHtml={p.html}
      imageUrl={null}
      images={p.photos}
      media={media}
      channelName=""
      top={
        p.forwarded_from ? (
          <>
            {t("autopost.phone.forwarded")} <b>{p.forwarded_from}</b>
          </>
        ) : undefined
      }
      extra={extra}
      footer={footer}
      className="max-w-[min(100%,30rem)]"
    />
  );
}
