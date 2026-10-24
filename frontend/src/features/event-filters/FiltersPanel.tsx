import { ChevronRightIcon, MinusIcon } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import { RelevanceIcon } from "@/entities/event";
import { useSourcesBrief } from "@/entities/source";
import { EntityMultiSelect, useSports } from "@/entities/taxonomy";
import { isoToLocalInput, localInputToIso, zoned, zoneLabel } from "@/shared/lib/datetime";
import { regionName } from "@/shared/lib/region";
import { PERIODS, type Period } from "@/shared/lib/search";
import {
  EVENT_STATUS,
  RELEVANCE,
  RELIABILITY,
  withDashboardDefaults,
  type DashboardSearch,
} from "@/shared/routing";
import { cn } from "@/shared/lib/utils";
import { Button, DateTimePicker, HelpTip, Hint, Input } from "@/shared/ui";

import { activeFiltersCount, periodError } from "./toApiFilters";
import { type FilterScope, useDashboardSearch } from "./useDashboardSearch";

/** Чип-переключатель: нативный checkbox (клавиатура, роль, label) в виде плашки.
 * relative обязателен: иначе sr-only input позиционируется от корня и растягивает страницу. */
function ChipCheck({
  id,
  checked,
  onChange,
  hint,
  children,
}: {
  id: string;
  checked: boolean;
  onChange: () => void;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <Hint text={hint}>
      <label
        htmlFor={id}
        className="border-input hover:border-foreground has-checked:border-brand-text relative rounded-md has-checked:text-brand-text has-checked:font-semibold has-focus-visible:outline-ring inline-flex min-h-8 cursor-pointer items-center gap-1.5 border-[1.5px] px-2 py-1 text-[13px] leading-tight has-focus-visible:outline-2 has-focus-visible:outline-offset-2"
      >
        <input id={id} type="checkbox" className="sr-only" checked={checked} onChange={onChange} />
        {children}
      </label>
    </Hint>
  );
}

const LEGEND = "text-muted-foreground mb-2 text-[11px] font-semibold tracking-[0.08em] uppercase";

/** Сворачиваемая группа (нативный details): в строке — что выбрано, список — по клику. */
function Group({
  legend,
  hint,
  summary,
  children,
}: {
  legend: string;
  hint?: string;
  summary: string;
  children: ReactNode;
}) {
  return (
    <details className="group/f">
      <summary className="flex min-h-8 cursor-pointer list-none items-center gap-1.5 rounded-md [&::-webkit-details-marker]:hidden">
        <ChevronRightIcon
          aria-hidden
          className="text-muted-foreground size-3.5 shrink-0 transition-transform group-open/f:rotate-90 motion-reduce:transition-none"
        />
        <span className={cn(LEGEND, "mb-0")}>{legend}</span>
        {hint ? <HelpTip text={hint} /> : null}
        <span className="text-muted-foreground ml-auto truncate pl-2 text-xs">{summary}</span>
      </summary>
      <div className="pt-2 pb-1">{children}</div>
    </details>
  );
}

/** «Футбол, Теннис +2» / «все» — итог выбора в строке группы. */
function summarize(names: string[], none: string, max = 2): string {
  if (!names.length) return none;
  const rest = names.length - max;
  return names.slice(0, max).join(", ") + (rest > 0 ? ` +${rest}` : "");
}

type SourceState = "on" | "off" | "excluded";

/** Источники: клик — только этот, второй — исключить, третий — снять. Поиск по названию. */
function SourceFilter({
  sources,
  include,
  exclude,
  onChange,
}: {
  sources: { id: string; name: string }[];
  include: string[];
  exclude: string[];
  onChange: (include: string[], exclude: string[]) => void;
}) {
  const { t } = useTranslation(["dashboard", "hints"]);
  const [q, setQ] = useState("");
  const state = (id: string): SourceState =>
    include.includes(id) ? "on" : exclude.includes(id) ? "excluded" : "off";
  const cycle = (id: string) => {
    const inc = include.filter((x) => x !== id);
    const exc = exclude.filter((x) => x !== id);
    const s = state(id);
    onChange(s === "off" ? [...inc, id] : inc, s === "on" ? [...exc, id] : exc);
  };
  const needle = q.trim().toLowerCase();
  const shown = sources.filter((x) => !needle || x.name.toLowerCase().includes(needle));
  return (
    <fieldset className="space-y-2" aria-label={t("source")}>
      {sources.length > 8 ? (
        <Input
          aria-label={t("find_source")}
          placeholder={t("find_source")}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-8"
        />
      ) : null}
      <div className="flex max-h-56 flex-wrap gap-1.5 overflow-y-auto">
        {shown.map((x) => {
          const s = state(x.id);
          return (
            <Hint key={x.id} text={t(`hints:source_state.${s}`)}>
              <button
                type="button"
                aria-pressed={s !== "off"}
                aria-label={s === "excluded" ? t("source_excluded", { name: x.name }) : x.name}
                onClick={() => cycle(x.id)}
                className={cn(
                  "border-input hover:border-foreground focus-visible:outline-ring inline-flex min-h-8 items-center gap-1 rounded-md border-[1.5px] px-2 py-1 text-[13px] leading-tight focus-visible:outline-2 focus-visible:outline-offset-2",
                  s === "on" && "border-brand-text text-brand-text font-semibold",
                  s === "excluded" && "border-destructive text-destructive line-through",
                )}
              >
                {s === "excluded" ? <MinusIcon aria-hidden className="size-3.5" /> : null}
                {x.name}
              </button>
            </Hint>
          );
        })}
        {!shown.length ? (
          <p className="text-muted-foreground text-xs">{t("nothing_found")}</p>
        ) : null}
      </div>
    </fieldset>
  );
}

function CheckGroup<T extends string>({
  name,
  legend,
  hint,
  options,
  values,
  label,
  optionHint,
  onChange,
  bare,
}: {
  name: string;
  legend: string;
  hint?: string;
  options: readonly T[];
  values: readonly string[];
  label: (v: T) => ReactNode;
  optionHint?: (v: T) => string;
  onChange: (values: T[]) => void;
  /** внутри сворачиваемой группы: заголовок уже в её строке */
  bare?: boolean;
}) {
  if (!options.length) return null;
  return (
    <fieldset className="space-y-2" aria-label={legend}>
      {bare ? null : (
        <legend className={LEGEND}>
          {legend}
          {hint ? <HelpTip text={hint} /> : null}
        </legend>
      )}
      <div className="flex flex-wrap gap-1.5">
        {options.map((o) => (
          <ChipCheck
            key={o}
            id={`f-${name}-${o}`}
            checked={values.includes(o)}
            hint={optionHint?.(o)}
            onChange={() =>
              onChange((values.includes(o) ? values.filter((v) => v !== o) : [...values, o]) as T[])
            }
          >
            {label(o)}
          </ChipCheck>
        ))}
      </div>
    </fieldset>
  );
}

/** Панель фильтров «Событий» и «Ленты» (общий выбор). В ленте нет статуса и периода:
 * там свои — всё, что ещё можно отправить, за последние 3 дня. */
export function FiltersPanel({
  timeZone,
  scope = "events",
}: {
  timeZone: string;
  scope?: FilterScope;
}) {
  const { t } = useTranslation(["dashboard", "enums", "common", "hints"]);
  const { search, set, reset } = useDashboardSearch(scope);
  const events = scope === "events";
  const s = withDashboardDefaults(search);
  const sports = useSports();
  const sources = useSourcesBrief();
  const count = activeFiltersCount(search);
  const list = <T,>(v: T[]) => (v.length ? v : undefined);
  const sportName = (v: string) =>
    v === "none" ? t("unclassified") : (sports.data?.find((x) => x.id === v)?.name ?? v);
  const sourceName = (v: string) => sources.data?.find((x) => x.id === v)?.name ?? "…";

  return (
    <aside aria-label={t("filters_title")} className="space-y-5 text-sm">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold">
          {t("filters_title")}
          {count ? ` (${count})` : ""}
        </h2>
        <Button variant="ghost" size="sm" disabled={count === 0} onClick={reset}>
          {t("clear_filters")}
        </Button>
      </div>

      {sports.isError ? (
        <p role="alert">
          {t("load_failed")}{" "}
          <Button variant="link" size="sm" onClick={() => void sports.refetch()}>
            {t("common:retry")}
          </Button>
        </p>
      ) : (
        <Group
          legend={t("sport")}
          hint={t("hints:filter.sport")}
          summary={summarize((s.sport ?? []).map(sportName), t("any"))}
        >
          <CheckGroup
            bare
            name="sport"
            legend={t("sport")}
            options={[...(sports.data ?? []).map((x) => x.id), "none"]}
            values={s.sport ?? []}
            label={sportName}
            onChange={(v) => set({ sport: list(v) })}
          />
        </Group>
      )}

      <Group
        legend={t("region")}
        hint={t("hints:filter.region")}
        summary={summarize(
          (s.region ?? []).map((c) => regionName(c)),
          t("any"),
        )}
      >
        <CheckGroup
          bare
          name="region"
          legend={t("region")}
          options={[...new Set((sources.data ?? []).map((x) => x.region).filter(Boolean))].sort()}
          values={s.region ?? []}
          label={(v) => regionName(v)}
          onChange={(v) => set({ region: list(v) })}
        />
      </Group>

      <EntityMultiSelect
        label={t("competition")}
        kind="competition"
        values={s.competition ?? []}
        onChange={(v) => set({ competition: list(v) })}
      />

      <CheckGroup
        name="relevance"
        legend={t("relevance")}
        hint={t("hints:filter.relevance")}
        optionHint={(v) => t(`hints:relevance.${v}`)}
        options={RELEVANCE}
        values={s.relevance}
        label={(v) => (
          <>
            <RelevanceIcon level={v} className="size-3.5" />
            {t(`enums:Relevance.${v}`)}
          </>
        )}
        onChange={(v) => set({ relevance: v })}
      />
      {s.relevance.length === 0 ? (
        <p className="text-destructive text-xs">{t("pick_relevance")}</p>
      ) : null}

      <CheckGroup
        name="reliability"
        legend={t("reliability")}
        hint={t("hints:filter.trust")}
        optionHint={(v) => t(`hints:trust.${v}`)}
        options={RELIABILITY}
        values={s.reliability ?? []}
        label={(v) => t(`enums:Reliability.${v}`)}
        onChange={(v) => set({ reliability: list(v) })}
      />

      <Group
        legend={t("source")}
        hint={t("hints:filter.source")}
        summary={summarize(
          [
            ...(s.source ?? []).map(sourceName),
            ...(s.xsource ?? []).map((id) => `−${sourceName(id)}`),
          ],
          t("any"),
        )}
      >
        <SourceFilter
          sources={sources.data ?? []}
          include={s.source ?? []}
          exclude={s.xsource ?? []}
          onChange={(inc, exc) => set({ source: list(inc), xsource: list(exc) })}
        />
      </Group>

      {events ? (
        <Group
          legend={t("status")}
          hint={t("hints:filter.status")}
          summary={t("n_of", { n: s.status.length, total: EVENT_STATUS.length })}
        >
          <CheckGroup
            bare
            name="status"
            legend={t("status")}
            optionHint={(v) => t(`hints:status.${v}`)}
            options={EVENT_STATUS}
            values={s.status}
            label={(v) => t(`enums:EventStatus.${v}`)}
            onChange={(v) => set({ status: v })}
          />
        </Group>
      ) : null}

      {events ? (
        <fieldset className="space-y-2" aria-label={t("common:filters.period")}>
          <legend className={LEGEND}>
            {t("common:filters.period")}
            <HelpTip text={t("hints:filter.period")} />
          </legend>
          <div className="flex flex-wrap gap-1" role="group">
            {PERIODS.map((p: Period) => (
              <Button
                key={p}
                size="sm"
                variant={s.period === p ? "default" : "outline"}
                aria-pressed={s.period === p}
                onClick={() =>
                  set(
                    p === "custom"
                      ? { period: p }
                      : ({
                          period: p === "24h" ? undefined : p,
                          from: undefined,
                          to: undefined,
                        } as Partial<DashboardSearch>),
                  )
                }
              >
                {p === "custom" ? t("custom") : t(`common:filters.periods.${p}`)}
              </Button>
            ))}
          </div>
          {s.period === "custom" ? (
            <div className="space-y-1">
              {(["from", "to"] as const).map((k) => (
                <div key={k} className="flex items-center gap-2">
                  <span className="w-6">{t(k)}</span>
                  <DateTimePicker
                    label={t(k)}
                    value={isoToLocalInput(s[k], timeZone)}
                    today={zoned(new Date(), timeZone).key}
                    zoneLabel={zoneLabel(timeZone)}
                    className={cn("flex-1", periodError(search) && "border-destructive")}
                    onChange={(v) => set({ [k]: localInputToIso(v, timeZone) })}
                  />
                </div>
              ))}
              {periodError(search) ? (
                <p className="text-destructive text-xs">{t("from_after_to")}</p>
              ) : null}
            </div>
          ) : null}
        </fieldset>
      ) : (
        <p className="text-muted-foreground text-xs">{t("feed_scope_note")}</p>
      )}

      <div className="flex items-center gap-1">
        <ChipCheck
          id="f-conflicts"
          checked={s.conflicts === "1"}
          onChange={() => set({ conflicts: s.conflicts === "1" ? undefined : "1" })}
        >
          {t("only_conflicts")}
        </ChipCheck>
        <HelpTip text={t("hints:filter.conflicts")} />
      </div>
    </aside>
  );
}
