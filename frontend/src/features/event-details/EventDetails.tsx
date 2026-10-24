import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AiEventStatus } from "@/entities/ai";
import {
  type ArticleInEvent,
  type EventDetail,
  RelevanceBadge,
  RelevanceRationale,
  ReliabilityBadge,
  StatusChip,
} from "@/entities/event";
import { useSportName } from "@/entities/taxonomy";
import { isAppError } from "@/shared/api";
import { formatDateTime, formatRelative } from "@/shared/lib/datetime";
import { isForeign, languageName, regionName } from "@/shared/lib/region";
import { cn } from "@/shared/lib/utils";
import { AiContentMark, Badge, Button, HelpTip, Hint, Skeleton } from "@/shared/ui";

import { splitCitations } from "./citations";
import { useEventDetail } from "./useEventDetail";
import { useViewHeartbeat } from "./useViewHeartbeat";

type Slot = ReactNode | ((e: EventDetail) => ReactNode);

export interface DetailSlots {
  actions?: Slot;
  edit?: Slot;
  relevanceAction?: Slot;
  /** Действия над статьёй события (перенос, FE-T4.4). */
  articleAction?: (e: EventDetail, a: ArticleInEvent) => ReactNode;
  reliabilityAction?: Slot;
  conflicts?: Slot;
  /** AI-бриф на выбранном языке (фаза 3). */
  brief?: Slot;
  draft?: Slot;
  history?: Slot;
}

const RELATION_GROUPS: [string[], string][] = [
  [["related", "follow_up"], "related"],
  [["possible_duplicate"], "possible_duplicate"],
  [["old_news"], "old_news"],
];

/** Заголовок раздела карточки: плотный, с подсказкой «?» справа. */
const H3 = "flex items-center gap-1 text-sm font-bold";

const fill = (slot: Slot | undefined, e: EventDetail) =>
  typeof slot === "function" ? slot(e) : slot;

/**
 * Детали события (FE-T2.27). Слоты фаз 3–4 заполняет страница: сам компонент не импортирует
 * другие фичи (правило слоёв).
 */
export function EventDetails({
  eventId,
  timeZone,
  slots = {},
  onClose,
  onSelectEvent,
  onAddEntity,
}: {
  eventId: string;
  timeZone: string;
  slots?: DetailSlots;
  onClose?: () => void;
  onSelectEvent?: (id: string) => void;
  onAddEntity?: (id: string) => void;
}) {
  const { t, i18n } = useTranslation(["event", "common", "hints"]);
  const q = useEventDetail(eventId);
  useViewHeartbeat(q.data ? eventId : undefined);
  const heading = useRef<HTMLHeadingElement>(null);
  const [cited, setCited] = useState<number | null>(null);
  useEffect(() => {
    if (q.data) heading.current?.focus();
  }, [eventId, q.data?.id]); // eslint-disable-line react-hooks/exhaustive-deps -- фокус только при смене события

  if (q.isPending)
    return (
      <div className="space-y-3 p-4" aria-busy="true">
        <Skeleton className="h-8 w-3/4" />
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  if (q.isError) {
    const notFound = isAppError(q.error) && q.error.status === 404;
    return (
      <div role="alert" className="space-y-2 p-4">
        <p>{notFound ? t("not_found") : t("load_failed")}</p>
        {notFound ? (
          onClose && (
            <Button variant="outline" onClick={onClose}>
              {t("close")}
            </Button>
          )
        ) : (
          <Button variant="outline" onClick={() => void q.refetch()}>
            {t("common:retry")}
          </Button>
        )}
      </div>
    );
  }
  const e = q.data;
  const articles = e.articles ?? [];
  // перевод, совпадающий с оригиналом (событие уже на языке UI), переводом не считается
  const titleTr = e.title_i18n[i18n.language] !== e.title ? e.title_i18n[i18n.language] : undefined;
  const citedArticle = cited
    ? e.summary?.citations.find((c) => c.n === cited)?.article_id
    : undefined;

  return (
    <article className="space-y-7 px-5 py-6 md:px-8" aria-labelledby="event-title">
      <header className="space-y-4">
        <h2
          id="event-title"
          ref={heading}
          tabIndex={-1}
          className="font-display text-xl leading-[1.15] font-bold outline-none md:text-[1.75rem]"
        >
          <Hint text={titleTr ? `${t("original")}: ${e.title}` : undefined}>
            <span>{titleTr ?? e.title}</span>
          </Hint>
        </h2>
        <div className="flex flex-wrap items-center gap-1.5">
          <RelevanceBadge level={e.relevance} />
          <ReliabilityBadge level={e.reliability} />
          <StatusChip status={e.status} />
          {e.title_origin === "ai" ? <AiContentMark /> : null}
          <OriginalLanguage e={e} />
        </div>
        <SourceComposition e={e} articles={articles} />
        <AiEventStatus eventId={e.id} kinds={["translate", "brief"]} />
        <div className="flex flex-wrap items-center gap-2">{fill(slots.actions, e)}</div>
      </header>
      {fill(slots.edit, e)}
      {fill(slots.conflicts, e)}
      <SummaryBlock e={e} articles={articles} onCite={setCited} />
      <MetaGrid e={e} timeZone={timeZone} onAddEntity={onAddEntity} />
      <section aria-label={t("why_relevant")} className="space-y-1">
        <h3 id="rel-h" className={H3}>
          {t("why_relevant")}
          <HelpTip text={t("hints:event.why")} />
          {fill(slots.relevanceAction, e)}
        </h3>
        <RelevanceRationale text={e.relevance_rationale} />
        {e.relevance_origin === "human" ? (
          <p className="text-muted-foreground text-xs">
            {t("adjusted", { reason: e.relevance_reason ?? "" })}
          </p>
        ) : null}
      </section>
      <ReliabilityBlock e={e} action={fill(slots.reliabilityAction, e)} />
      <section aria-label={t("sources_title", { count: articles.length })} className="space-y-2">
        <h3 id="src-h" className={H3}>
          {t("sources_title", { count: articles.length })}
          <HelpTip text={t("hints:event.sources")} />
        </h3>
        <ul className="border-t">
          {articles.map((a) => (
            <SourceItem
              key={a.id}
              a={a}
              timeZone={timeZone}
              highlighted={a.id === citedArticle}
              action={slots.articleAction?.(e, a)}
            />
          ))}
        </ul>
      </section>
      {e.related?.length ? (
        <section aria-label={t("related")} className="space-y-2">
          <h3 id="related-h" className={H3}>
            {t("related")}
            <HelpTip text={t("hints:event.related")} />
          </h3>
          {RELATION_GROUPS.map(([kinds, label]) => {
            const items = (e.related ?? []).filter((r) => kinds.includes(r.kind));
            return items.length ? (
              <div key={label} className="space-y-1">
                <h4 className="text-muted-foreground text-xs font-medium">
                  {t(`related_groups.${label}`)}
                </h4>
                <ul className="space-y-1">
                  {items.map((r) => (
                    <li key={`${r.id}-${r.kind}`}>
                      <button
                        type="button"
                        className="flex items-center gap-2 text-left text-sm hover:underline"
                        onClick={() => onSelectEvent?.(r.id)}
                      >
                        {r.title}
                        <span className="text-muted-foreground text-xs">
                          {formatRelative(r.last_article_at)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null;
          })}
        </section>
      ) : null}
      {fill(slots.brief, e)}
      {fill(slots.draft, e)}
      {fill(slots.history, e)}
    </article>
  );
}

/** «Оригинал: португальский» или «Переводится…», пока сервер переводит событие. */
function OriginalLanguage({ e }: { e: EventDetail }) {
  const { t } = useTranslation("event");
  if (e.translation_pending)
    return (
      <span role="status" className="text-muted-foreground animate-pulse text-xs">
        {t("translating")}
      </span>
    );
  const lang = e.original_language;
  if (!lang) return null;
  return (
    <Hint text={isForeign(lang) ? t("original_hint", { title: e.title }) : t("same_language")}>
      <Badge variant="outline" className="cursor-help">
        {t("original_language", { language: languageName(lang) })}
      </Badge>
    </Hint>
  );
}

function SummaryBlock({
  e,
  articles,
  onCite,
}: {
  e: EventDetail;
  articles: ArticleInEvent[];
  onCite: (n: number | null) => void;
}) {
  const { t, i18n } = useTranslation("event");
  if (!e.summary)
    return (
      <section aria-label={t("summary")} className="space-y-1">
        <SummaryHeading />
        <p className="text-muted-foreground text-sm">{t("no_summary")}</p>
        {articles.slice(0, 2).map((a) =>
          a.lead ? (
            <p key={a.id} className="text-sm">
              {a.lead}
            </p>
          ) : null,
        )}
      </section>
    );
  const s = e.summary;
  const translated =
    s.translations[i18n.language] !== s.text ? s.translations[i18n.language] : undefined;
  const byId = new Map(articles.map((a) => [a.id, a]));
  // ponytail: волнистое подчёркивание непроверенных предложений — когда появится grounding (фаза L, BE-T2.18)
  return (
    <section aria-label={t("summary")} className="space-y-1">
      <SummaryHeading />
      {s.origin === "ai" ? <AiContentMark variant="block" /> : null}
      {translated ? (
        <p className="text-muted-foreground text-xs">
          <Hint text={s.text}>
            <span className="cursor-help underline decoration-dotted">{t("translated")}</span>
          </Hint>
        </p>
      ) : null}
      <p className="max-w-[68ch] text-[15px] leading-relaxed">
        {splitCitations(translated ?? s.text).map((p, i) => {
          if (p.kind === "text") return <span key={i}>{p.text}</span>;
          const art = byId.get(s.citations.find((c) => c.n === p.n)?.article_id ?? "");
          return (
            <button
              key={i}
              type="button"
              disabled={!art}
              title={art ? undefined : t("source_removed")}
              aria-label={
                art ? t("cite", { n: p.n, source: art.source?.name ?? "" }) : t("source_removed")
              }
              className="text-brand-text mx-0.5 align-super text-xs font-bold hover:underline disabled:opacity-50"
              onMouseEnter={() => onCite(p.n)}
              onMouseLeave={() => onCite(null)}
              onClick={() => onCite(p.n)}
            >
              [{p.n}]
            </button>
          );
        })}
      </p>
    </section>
  );
}

function MetaGrid({
  e,
  timeZone,
  onAddEntity,
}: {
  e: EventDetail;
  timeZone: string;
  onAddEntity?: (id: string) => void;
}) {
  const { t } = useTranslation(["event", "dashboard"]);
  const sportName = useSportName();
  const chips = (items: { id: string; name: string }[]) =>
    items.length ? (
      <span className="flex flex-wrap gap-1">
        {items.map((x) => (
          <button
            key={x.id}
            type="button"
            className="bg-secondary hover:bg-accent rounded-sm px-1.5 py-0.5 text-xs font-medium"
            onClick={() => onAddEntity?.(x.id)}
          >
            {x.name}
          </button>
        ))}
      </span>
    ) : (
      "—"
    );
  const rows: [string, ReactNode][] = [
    [t("occurred_at"), formatDateTime(e.occurred_at, timeZone)],
    [t("updated"), formatDateTime(e.last_article_at, timeZone)],
    [t("dashboard:sport"), e.sport_id ? sportName(e.sport_id) : t("dashboard:unclassified")],
    [t("region"), e.region ? regionName(e.region) : "—"],
    [t("dashboard:competition"), e.competition?.name ?? "—"],
    [t("teams"), chips(e.teams)],
    [t("players"), chips(e.players)],
  ];
  return (
    <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1 text-sm">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-muted-foreground">{k}</dt>
          <dd>{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function SummaryHeading() {
  const { t } = useTranslation(["event", "hints"]);
  return (
    <h3 className={H3}>
      {t("summary")}
      <HelpTip text={t("hints:event.summary")} />
    </h3>
  );
}

function ReliabilityBlock({ e, action }: { e: EventDetail; action?: ReactNode }) {
  const { t } = useTranslation(["event", "enums", "hints"]);
  return (
    <section aria-label={t("reliability_title")} className="space-y-1">
      <h3 id="relia-h" className={H3}>
        {t("reliability_title")}: {t(`enums:Reliability.${e.reliability}`)}
        <HelpTip text={t("hints:event.trust")} />
        {action}
      </h3>
      <details>
        <summary className="cursor-pointer text-sm">{t("factors")}</summary>
        <ul className="mt-1 list-disc pl-5 text-sm">
          {e.reliability_factors.map((f) => (
            <li key={f.code}>
              {t(`enums:ReliabilityFactor.${f.code}`)}
              {f.detail ? <span className="text-muted-foreground"> · {f.detail}</span> : null}
            </li>
          ))}
        </ul>
      </details>
      {e.reliability_origin === "human" ? (
        <p className="text-muted-foreground text-xs">
          {t("adjusted", { reason: e.reliability_reason ?? "" })}
        </p>
      ) : null}
    </section>
  );
}

function SourceItem({
  a,
  timeZone,
  highlighted,
  action,
}: {
  a: ArticleInEvent;
  timeZone: string;
  highlighted: boolean;
  action?: ReactNode;
}) {
  const { t } = useTranslation(["event", "hints", "enums"]);
  // перевод на язык интерфейса; у статей на том же языке он совпадает с оригиналом
  const tr =
    a.translation && (a.translation.title !== a.title || a.translation.lead !== a.lead)
      ? a.translation
      : null;
  const lang = a.source?.language;
  const tags = [
    a.is_duplicate && t("tag.duplicate"),
    a.manual && t("tag.manual"),
    a.rumor_markers.length > 0 && t("tag.rumor"),
    a.clickbait && t("tag.clickbait"),
  ].filter(Boolean) as string[];
  return (
    <li
      id={`src-${a.id}`}
      data-highlighted={highlighted}
      className={cn(
        "scroll-mt-4 border-b py-3 text-sm",
        highlighted && "bg-accent outline-primary -mx-2 px-2 outline-2",
      )}
    >
      <div className="text-muted-foreground flex flex-wrap items-center gap-2 text-xs">
        <span className="font-medium">{a.source?.name ?? "—"}</span>
        {a.source?.tier ? (
          <Hint text={t(`hints:tier.${a.source.tier}`, { defaultValue: "" })}>
            <Badge variant="outline">
              {t(`enums:SourceTier.${a.source.tier}`, { defaultValue: a.source.tier })}
            </Badge>
          </Hint>
        ) : null}
        <span>{formatDateTime(a.published_at ?? a.discovered_at, timeZone)}</span>
        {lang ? (
          <Hint text={t("written_in", { language: languageName(lang) })}>
            <Badge variant="outline" className="cursor-help uppercase">
              {lang.split("-")[0]}
            </Badge>
          </Hint>
        ) : null}
        {tags.map((x) => (
          <Badge key={x} variant="secondary">
            {x}
          </Badge>
        ))}
        {action}
      </div>
      <a
        href={a.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-1 block font-semibold hover:underline"
      >
        <Hint text={tr ? `${t("original")}: ${a.title}` : undefined}>
          <span>{tr?.title ?? a.title}</span>
        </Hint>
      </a>
      {(tr?.lead ?? a.lead) ? (
        <p className="text-muted-foreground mt-0.5 line-clamp-2">{tr?.lead ?? a.lead}</p>
      ) : null}
      {a.source?.health === "down" ? (
        <p className="text-destructive text-xs">{t("source_down")}</p>
      ) : null}
    </li>
  );
}

/**
 * Подтверждение геометрией: блок на каждое издание.
 * Залитый — независимое (первое в своей медиагруппе), контурный — повтор той же группы.
 * Клик по блоку ведёт к статье этого издания в списке источников.
 */
function SourceComposition({ e, articles }: { e: EventDetail; articles: ArticleInEvent[] }) {
  const { t } = useTranslation(["dashboard", "event", "hints"]);
  const seenGroups = new Set<string>();
  const blocks: { id: string; name: string; tier: string | null; independent: boolean }[] = [];
  const seenSources = new Set<string>();
  for (const a of articles) {
    const src = a.source;
    if (!src || seenSources.has(src.id)) continue;
    seenSources.add(src.id);
    const group = src.owner_group ?? src.id;
    blocks.push({ id: a.id, name: src.name, tier: src.tier, independent: !seenGroups.has(group) });
    seenGroups.add(group);
  }
  if (!blocks.length) return null;
  const summary =
    e.independent_source_count < e.source_count
      ? t("sources_independent", { count: e.source_count, independent: e.independent_source_count })
      : t("sources", { count: e.source_count });
  return (
    <figure className="space-y-2">
      <ul
        aria-label={summary}
        className="grid grid-cols-[repeat(auto-fill,minmax(6.5rem,1fr))] gap-1"
      >
        {blocks.map((b, i) => (
          <li
            key={b.id}
            className="compose-in"
            style={{ transitionDelay: `${Math.min(i, 10) * 30}ms` }}
          >
            <Hint text={b.independent ? t("hints:block.independent") : t("hints:block.same_group")}>
              <a
                href={`#src-${b.id}`}
                className={cn(
                  "flex h-16 flex-col justify-between rounded-md p-2 text-xs font-semibold transition-colors",
                  b.independent
                    ? "bg-primary text-primary-foreground hover:bg-primary/85"
                    : "border-primary text-brand-text hover:bg-accent border-2",
                )}
              >
                <span className="line-clamp-2 leading-tight">{b.name}</span>
                <span className="text-xs font-medium">
                  {b.independent ? t("event:block_independent") : t("event:block_same_group")}
                  {b.tier ? ` · ${b.tier}` : ""}
                </span>
              </a>
            </Hint>
          </li>
        ))}
      </ul>
      <figcaption className="text-muted-foreground flex items-center gap-1 text-xs">
        {summary}
        <HelpTip text={t("hints:badge.sources")} />
      </figcaption>
    </figure>
  );
}
