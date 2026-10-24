import { SparklesIcon } from "lucide-react";
import { memo } from "react";
import { useTranslation } from "react-i18next";

import {
  ConfirmationSquares,
  EventFlags,
  type EventListItem,
  RelevanceBadge,
  ReliabilityBadge,
  StatusChip,
} from "@/entities/event";
import { SourceMark } from "@/entities/source";
import { useSystemStatus } from "@/entities/user";
import { formatRelative } from "@/shared/lib/datetime";
import { looksLike } from "@/shared/lib/lang";
import { cn } from "@/shared/lib/utils";
import { Hint } from "@/shared/ui";

import { rowId } from "./rowMeta";

function Row({
  e,
  selected,
  fresh,
  height,
  onSelect,
  onPrefetch,
}: {
  e: EventListItem;
  selected: boolean;
  /** Позиция в списке, если событие только что добавлено (для шага анимации). */
  fresh?: number;
  height: number;
  onSelect: (id: string) => void;
  onPrefetch?: (id: string) => void;
}) {
  const { t, i18n } = useTranslation(["dashboard", "hints"]);
  const aiOn = useSystemStatus()?.ai.llm.available ?? false;
  const sources =
    e.independent_source_count < e.source_count
      ? t("sources_independent", { count: e.source_count, independent: e.independent_source_count })
      : t("sources", { count: e.source_count });
  const retired = e.status === "REJECTED";
  return (
    <div
      id={rowId(e.id)}
      role="option"
      aria-selected={selected}
      tabIndex={-1}
      onClick={() => onSelect(e.id)}
      onKeyDown={(k) => (k.key === "Enter" || k.key === " ") && onSelect(e.id)}
      onMouseEnter={() => onPrefetch?.(e.id)}
      onFocus={() => onPrefetch?.(e.id)}
      style={{ height, ["--i" as string]: fresh !== undefined ? Math.min(fresh, 8) : undefined }}
      className={cn(
        "grid cursor-pointer grid-cols-[auto_minmax(0,1fr)_auto] content-center gap-x-3 gap-y-1 border-b px-3 text-sm",
        selected ? "row-selected" : "hover:bg-accent",
        retired && !selected && "text-muted-foreground grayscale",
        fresh !== undefined && "row-fresh",
      )}
    >
      <div className="row-span-2 self-center">
        <SourceMark top={e.top_sources} total={e.source_count} />
      </div>
      <div className="flex min-w-0 items-start gap-1.5 leading-snug font-semibold">
        <Hint text={e.title_i18n[i18n.language] ? e.title : undefined}>
          <span className="line-clamp-2 md:truncate">{e.title_i18n[i18n.language] ?? e.title}</span>
        </Hint>
        {!e.title_i18n[i18n.language] && aiOn && !looksLike(e.title, i18n.language) ? (
          <Hint text={t("hints:list.translating")}>
            <span className="text-muted-foreground mt-0.5 shrink-0 text-[11px] font-normal">
              {t("translating")}
            </span>
          </Hint>
        ) : null}
        {e.title_origin === "ai" ? (
          <Hint text={t("ai_title")}>
            <SparklesIcon
              role="img"
              aria-label={t("ai_title")}
              className="text-ai-text mt-0.5 size-3.5 shrink-0"
            />
          </Hint>
        ) : null}
      </div>
      <time
        dateTime={e.last_article_at}
        className="text-muted-foreground self-center text-xs font-medium"
      >
        {formatRelative(e.last_article_at, new Date(), i18n.language)}
      </time>
      <div className="col-span-2 flex min-w-0 items-center gap-1.5 overflow-hidden">
        <RelevanceBadge level={e.relevance} />
        <ReliabilityBadge level={e.reliability} />
        <StatusChip status={e.status} />
        <Hint text={t("hints:badge.sources")}>
          <span className="text-muted-foreground ml-1 inline-flex min-w-0 items-center gap-1.5 text-xs">
            <ConfirmationSquares total={e.source_count} independent={e.independent_source_count} />
            <span className="truncate">{sources}</span>
          </span>
        </Hint>
        <EventFlags e={e} />
      </div>
    </div>
  );
}

// Мемоизация по id + version: polling заменяет объекты, но строка перерисуется только при изменении.
export const EventRow = memo(
  Row,
  (a, b) =>
    a.e.id === b.e.id &&
    a.e.version === b.e.version &&
    a.selected === b.selected &&
    a.fresh === b.fresh &&
    a.height === b.height &&
    a.onSelect === b.onSelect,
);
