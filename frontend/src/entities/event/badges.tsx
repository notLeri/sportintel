import {
  ChevronsUpIcon,
  ChevronUpIcon,
  CircleSlashIcon,
  MinusIcon,
  ShieldAlertIcon,
  ShieldCheckIcon,
  ShieldIcon,
  ShieldQuestionIcon,
  TriangleAlertIcon,
} from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/utils";
import type { EventStatus, Relevance, Reliability } from "@/shared/routing";
import { Badge, Hint } from "@/shared/ui";

/*
 * Уровень читается без цвета — иконка + текст (WCAG 1.4.1).
 * Важность: высокая — жёлтая плашка, средняя — обводка, низкая — приглушённая.
 * Доверие: высокое — плашка акцента палитры, среднее — обводка акцентом, низкое — предупреждение.
 */
const RELEVANCE_TONE: Record<Relevance, string> = {
  HIGH: "bg-attention text-attention-foreground",
  MEDIUM: "ring-1 ring-inset ring-input text-foreground",
  LOW: "bg-muted text-muted-foreground",
  IRRELEVANT: "text-muted-foreground border border-dashed border-border",
};

const RELIABILITY_TONE: Record<Reliability, string> = {
  HIGH: "bg-primary text-primary-foreground",
  MEDIUM: "ring-1 ring-inset ring-brand-text/70 text-brand-text",
  LOW: "bg-warn-bg text-warn",
  UNKNOWN: "bg-muted text-muted-foreground",
};

const RELIABILITY_ICON = {
  HIGH: ShieldCheckIcon,
  MEDIUM: ShieldIcon,
  LOW: ShieldAlertIcon,
  UNKNOWN: ShieldQuestionIcon,
} satisfies Record<Reliability, unknown>;

const RELEVANCE_LUCIDE = {
  HIGH: ChevronsUpIcon,
  MEDIUM: ChevronUpIcon,
  LOW: MinusIcon,
  IRRELEVANT: CircleSlashIcon,
} satisfies Record<Relevance, unknown>;

export function RelevanceIcon({ level, className }: { level: string; className?: string }) {
  const Icon = RELEVANCE_LUCIDE[level as Relevance] ?? MinusIcon;
  return <Icon aria-hidden strokeWidth={2.5} className={className} />;
}

export function RelevanceBadge({ level }: { level: string }) {
  const { t } = useTranslation(["enums", "hints"]);
  const l = level as Relevance;
  return (
    <Hint text={`${t("hints:badge.relevance")}. ${t(`hints:relevance.${l}`)}`}>
      <Badge variant="outline" className={cn("gap-1 border-0 font-semibold", RELEVANCE_TONE[l])}>
        <RelevanceIcon level={l} />
        {t(`enums:RelevanceBadge.${l}`)}
      </Badge>
    </Hint>
  );
}

export function ReliabilityBadge({ level }: { level: string }) {
  const { t } = useTranslation(["enums", "hints"]);
  const l = level as Reliability;
  const Icon = RELIABILITY_ICON[l] ?? ShieldQuestionIcon;
  return (
    <Hint text={`${t("hints:badge.trust")}. ${t(`hints:trust.${l}`)}`}>
      <Badge variant="outline" className={cn("gap-1 border-0 font-semibold", RELIABILITY_TONE[l])}>
        <Icon aria-hidden strokeWidth={2.25} />
        {t(`enums:ReliabilityBadge.${l}`)}
      </Badge>
    </Hint>
  );
}

const STATUS_TONE: Partial<Record<EventStatus, string>> = {
  READY: "bg-primary text-primary-foreground",
  PUBLISHED: "bg-ai text-ai-foreground",
  REJECTED: "text-retired border border-current",
};

export function StatusChip({ status }: { status: string }) {
  const { t } = useTranslation(["enums", "hints"]);
  const s = status as EventStatus;
  return (
    <Hint text={t(`hints:status.${s}`)}>
      <Badge variant="secondary" className={STATUS_TONE[s]}>
        {t(`enums:EventStatus.${s}`)}
      </Badge>
    </Hint>
  );
}

/**
 * Подтверждение геометрией: квадрат на каждое издание,
 * залитый — независимое, контурный — из той же медиагруппы. Рядом всегда текст с числами.
 */
export function ConfirmationSquares({
  total,
  independent,
  max = 8,
  className,
}: {
  total: number;
  independent: number;
  max?: number;
  className?: string;
}) {
  const shown = Math.min(total, max);
  return (
    <span aria-hidden className={cn("text-brand-text inline-flex items-center gap-0.5", className)}>
      {Array.from({ length: shown }, (_, i) => (
        <span
          key={i}
          className={cn(
            "size-2.5 shrink-0 rounded-[2px]",
            i < independent ? "bg-current" : "border-[1.5px] border-current",
          )}
        />
      ))}
      {total > max ? (
        <span className="ml-0.5 text-[10px] font-semibold">+{total - max}</span>
      ) : null}
    </span>
  );
}

export function EventFlags({
  e,
}: {
  e: {
    has_open_conflicts: boolean;
    stale_suspected: boolean;
    has_clickbait: boolean;
    has_updates_since_edit: boolean;
  };
}) {
  const { t } = useTranslation(["dashboard", "hints"]);
  const flags = [
    e.has_open_conflicts && [t("flag.conflict"), t("hints:filter.conflicts"), true],
    e.stale_suspected && [t("flag.stale"), t("flag.stale_hint"), false],
    e.has_clickbait && [t("flag.clickbait"), t("flag.clickbait_hint"), false],
    e.has_updates_since_edit && [t("flag.updated"), "", false],
  ].filter(Boolean) as [string, string, boolean][];
  return flags.length ? (
    <span className="flex gap-1">
      {flags.map(([f, hint, alert]) => (
        <Hint key={f} text={hint}>
          <span className="bg-warn-bg text-warn inline-flex items-center gap-1 px-1 text-xs font-medium">
            {alert ? <TriangleAlertIcon aria-hidden className="size-3" /> : null}
            {f}
          </span>
        </Hint>
      ))}
    </span>
  ) : null;
}
