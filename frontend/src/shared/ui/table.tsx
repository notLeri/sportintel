import type { ComponentProps } from "react";

import { cn } from "@/shared/lib/utils";

/**
 * Таблица данных: карточка с рамкой, отступы ячеек, шапка без переносов (стили — .data-table в styles.css).
 * scroll — длинный список: прокрутка внутри карточки, шапка остаётся на месте.
 * Узкий экран — горизонтальная прокрутка вместо наезжающих колонок.
 * Ячейки: className="num" — число вправо, "shrink" — колонка по содержимому без переносов.
 */
export function DataTable({
  scroll,
  className,
  wrapClassName,
  ...props
}: ComponentProps<"table"> & { scroll?: boolean; wrapClassName?: string }) {
  return (
    <div
      className={cn(
        "bg-card overflow-x-auto rounded-lg border",
        // --table-top: высота всего, что над таблицей (шапка страницы, фильтры), чтобы она доходила до низа экрана.
        scroll && "max-h-[calc(100dvh-var(--table-top,15rem))] min-h-64 overflow-y-auto",
        wrapClassName,
      )}
    >
      <table className={cn("data-table", className)} {...props} />
    </div>
  );
}

export type StatusTone = "success" | "warn" | "danger" | "info" | "neutral";

const DOT: Record<StatusTone, string> = {
  success: "bg-success",
  warn: "bg-warn",
  danger: "bg-destructive",
  info: "bg-ai",
  neutral: "bg-muted-foreground/50",
};

/** Статус в таблице: точка + текст. Спокойнее заливки в длинных списках, читается без цвета. */
export function StatusDot({
  tone,
  className,
  children,
  ...props
}: ComponentProps<"span"> & { tone: StatusTone }) {
  return (
    <span
      className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}
      {...props}
    >
      <span aria-hidden className={cn("size-2 shrink-0 rounded-full", DOT[tone])} />
      {children}
    </span>
  );
}
