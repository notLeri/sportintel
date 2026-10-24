import { CalendarIcon, ChevronLeftIcon, ChevronRightIcon } from "lucide-react";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/utils";

import { Button } from "./button";
import { Popover, PopoverContent, PopoverTrigger } from "./popover";

// Значение — «настенное» время в нужном поясе, как у <input type="datetime-local">: "2026-10-12T15:30".
// Пересчёт в UTC — снаружи (shared/lib/datetime: fromLocalInput / toLocalInput).
const pad = (n: number) => String(n).padStart(2, "0");
const ymd = (y: number, m: number, d: number) => `${y}-${pad(m + 1)}-${pad(d)}`;
const asUtc = (day: string, hm = "12:00") => new Date(`${day}T${hm}:00Z`);

/** Понедельник — первый день недели, кроме en и pt (там воскресенье). */
function firstWeekday(lang: string): 0 | 1 {
  return /^(en|pt)/.test(lang) ? 0 : 1;
}

function monthDays(year: number, month: number, first: 0 | 1): string[] {
  const start = new Date(Date.UTC(year, month, 1));
  const shift = (start.getUTCDay() - first + 7) % 7;
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(Date.UTC(year, month, 1 - shift + i));
    return ymd(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
  });
}

function addDays(day: string, n: number): string {
  const d = asUtc(day);
  d.setUTCDate(d.getUTCDate() + n);
  return ymd(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

/** Выбор даты и времени: месяц с кружками дней и колонка времени с шагом step минут. */
export function DateTimePicker({
  value,
  onChange,
  label,
  min,
  today,
  zoneLabel,
  step = 15,
  placeholder,
  className,
  id,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  /** Раньше этого нельзя (то же «настенное» время). */
  min?: string;
  /** Сегодня в нужном поясе — "YYYY-MM-DD"; подсвечивается. */
  today?: string;
  /** Подпись пояса под календарём: «Москва · GMT+3». */
  zoneLabel?: string;
  step?: number;
  placeholder?: string;
  className?: string;
  id?: string;
}) {
  const { t, i18n } = useTranslation("common");
  const lang = i18n.language;
  const [open, setOpen] = useState(false);
  const [day, hm] = value ? (value.split("T") as [string, string]) : ["", ""];
  const base = day || min?.slice(0, 10) || today || ymd(2026, 0, 1);
  const [view, setView] = useState(() => ({ y: +base.slice(0, 4), m: +base.slice(5, 7) - 1 }));
  const [focus, setFocus] = useState(base);
  // выбранный, но ещё не подтверждённый день: значение меняется только выбором времени
  const [picked, setPicked] = useState(day);
  const grid = useRef<HTMLDivElement>(null);
  const times = useRef<HTMLDivElement>(null);
  const first = firstWeekday(lang);
  const days = useMemo(() => monthDays(view.y, view.m, first), [view, first]);
  const minDay = min?.slice(0, 10);

  useEffect(() => {
    if (!open) return;
    setView({ y: +base.slice(0, 4), m: +base.slice(5, 7) - 1 });
    setFocus(base);
    setPicked(day);
    // выбранное время — в видимой части колонки
    requestAnimationFrame(() =>
      times.current?.querySelector("[aria-selected=true]")?.scrollIntoView?.({ block: "center" }),
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps -- только при открытии
  }, [open]);

  const fmt = (o: Intl.DateTimeFormatOptions, d: Date) =>
    new Intl.DateTimeFormat(lang, { ...o, timeZone: "UTC" }).format(d);
  const title = fmt({ month: "long", year: "numeric" }, new Date(Date.UTC(view.y, view.m, 1)));
  const weekdays = days.slice(0, 7).map((d) => fmt({ weekday: "short" }, asUtc(d)));
  const shown = value
    ? fmt(
        { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" },
        asUtc(day, hm),
      )
    : (placeholder ?? t("datepicker.pick"));
  const slots = Array.from({ length: (24 * 60) / step }, (_, i) => {
    const mins = i * step;
    return `${pad(Math.floor(mins / 60))}:${pad(mins % 60)}`;
  });
  const pickDay = (d: string) => {
    if (minDay && d < minDay) return;
    setFocus(d);
    setPicked(d);
    // к выбранному времени — прокрутить колонку, если оно есть; иначе к первому доступному
    requestAnimationFrame(() =>
      (
        times.current?.querySelector("[aria-selected=true]") ??
        times.current?.querySelector("button:not(:disabled)")
      )?.scrollIntoView?.({ block: "center" }),
    );
  };
  const move = (d: string) => {
    setFocus(d);
    const y = +d.slice(0, 4);
    const m = +d.slice(5, 7) - 1;
    if (y !== view.y || m !== view.m) setView({ y, m });
    requestAnimationFrame(() =>
      grid.current?.querySelector<HTMLButtonElement>(`[data-day="${d}"]`)?.focus(),
    );
  };
  const onKey = (e: KeyboardEvent) => {
    const delta = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (delta) {
      e.preventDefault();
      move(addDays(focus, delta));
    }
  };
  const shiftMonth = (n: number) =>
    setView((v) => {
      const d = new Date(Date.UTC(v.y, v.m + n, 1));
      return { y: d.getUTCFullYear(), m: d.getUTCMonth() };
    });

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          size="sm"
          aria-label={value ? `${label}: ${shown}` : label}
          className={cn(
            "justify-start font-normal tabular-nums",
            !value && "text-muted-foreground",
            className,
          )}
        >
          <CalendarIcon aria-hidden className="opacity-70" />
          <span className="truncate capitalize">{shown}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-auto p-0" aria-label={label}>
        <div className="flex">
          <div className="p-3">
            <div className="mb-2 flex items-center justify-between gap-2 pl-1">
              <span aria-live="polite" className="text-[15px] font-medium capitalize">
                {title}
              </span>
              <div className="text-primary flex">
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="text-primary size-8"
                  aria-label={t("datepicker.prev_month")}
                  onClick={() => shiftMonth(-1)}
                >
                  <ChevronLeftIcon aria-hidden />
                </Button>
                <Button
                  type="button"
                  size="icon"
                  variant="ghost"
                  className="text-primary size-8"
                  aria-label={t("datepicker.next_month")}
                  onClick={() => shiftMonth(1)}
                >
                  <ChevronRightIcon aria-hidden />
                </Button>
              </div>
            </div>
            <div
              role="grid"
              tabIndex={-1}
              aria-label={title}
              ref={grid}
              onKeyDown={onKey}
              className="space-y-1"
            >
              <div role="row" className="grid grid-cols-7">
                {weekdays.map((w) => (
                  <span
                    key={w}
                    role="columnheader"
                    className="text-muted-foreground flex h-8 items-center justify-center text-xs capitalize"
                  >
                    {w}
                  </span>
                ))}
              </div>
              {[0, 1, 2, 3, 4, 5].map((r) => (
                <div role="row" key={r} className="grid grid-cols-7 gap-y-1">
                  {days.slice(r * 7, r * 7 + 7).map((d) => {
                    const outside = +d.slice(5, 7) - 1 !== view.m;
                    const disabled = Boolean(minDay && d < minDay);
                    const selected = d === picked;
                    return (
                      <span
                        role="gridcell"
                        key={d}
                        aria-selected={selected}
                        className="flex justify-center"
                      >
                        <button
                          type="button"
                          data-day={d}
                          tabIndex={d === focus ? 0 : -1}
                          disabled={disabled}
                          aria-label={fmt(
                            { weekday: "long", day: "numeric", month: "long", year: "numeric" },
                            asUtc(d),
                          )}
                          aria-current={d === today ? "date" : undefined}
                          onClick={() => pickDay(d)}
                          className={cn(
                            "focus-visible:ring-ring flex size-9 items-center justify-center rounded-full text-sm tabular-nums transition-colors outline-none focus-visible:ring-2",
                            "hover:bg-accent",
                            outside && "text-muted-foreground/50",
                            d === today && !selected && "text-primary font-semibold",
                            selected &&
                              "bg-primary text-primary-foreground hover:bg-primary font-semibold",
                            disabled && "pointer-events-none opacity-30",
                          )}
                        >
                          {+d.slice(8)}
                        </button>
                      </span>
                    );
                  })}
                </div>
              ))}
            </div>
            {zoneLabel ? (
              <p className="text-muted-foreground mt-2 pl-1 text-xs">
                {t("datepicker.zone", { zone: zoneLabel })}
              </p>
            ) : null}
          </div>
          <div
            ref={times}
            role="listbox"
            aria-label={t("datepicker.time")}
            className="max-h-[19rem] w-[5.5rem] overflow-y-auto border-l p-1.5"
          >
            {slots.map((s) => {
              const d = picked || focus;
              const disabled = Boolean(min && `${d}T${s}` < min);
              const selected = Boolean(value) && d === day && s === hm;
              return (
                <button
                  key={s}
                  type="button"
                  role="option"
                  aria-selected={selected}
                  disabled={disabled}
                  onClick={() => {
                    onChange(`${d}T${s}`);
                    setOpen(false);
                  }}
                  className={cn(
                    "hover:bg-accent block w-full rounded-full px-2 py-1 text-center text-sm tabular-nums",
                    selected && "bg-primary text-primary-foreground hover:bg-primary font-semibold",
                    disabled && "pointer-events-none opacity-30",
                  )}
                >
                  {s}
                </button>
              );
            })}
          </div>
        </div>
      </PopoverContent>
    </Popover>
  );
}
