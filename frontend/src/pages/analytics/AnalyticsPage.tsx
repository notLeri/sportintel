import { useQuery } from "@tanstack/react-query";
import { getRouteApi } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, unwrap } from "@/shared/api";
import { Button, DataTable, HelpTip, Input } from "@/shared/ui";

import { AiLoad } from "./AiLoad";

const route = getRouteApi("/analytics");
const MAX_DAYS = 92;

interface Row {
  key: string;
  label: string;
  useful_stories: number;
  active_hours: number;
  uspH: number | null;
}
interface Summary {
  totals: {
    useful_stories: number;
    active_hours: number;
    uspH: number | null;
    events_new: number;
    ai_cost_usd: number;
    ai_cost_per_useful: number | null;
  };
  rows: Row[];
  funnel: { status: string; count: number }[];
  time_to_select_p50_min: number | null;
  reject_reasons: { reason: string; count: number }[];
  precision_high: number | null;
  precision_high_by_origin: Record<string, number>;
  draft_edit_ratio_p50: number | null;
  draft_edit_ratio_p50_by_origin: Record<string, number | null>;
  feed_funnel: { suggested: number; taken: number; published: number };
  first_source_leaders: { source_id: string; name: string; useful_first_count: number }[];
}

const day = (d: Date) => d.toISOString().slice(0, 10);
const pct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`;

function Bars({
  items,
  label,
}: {
  items: { key: string; label: string; value: number }[];
  label: string;
}) {
  const max = Math.max(1, ...items.map((i) => i.value));
  return (
    <ul aria-label={label} className="space-y-1 text-sm">
      {items.map((i) => (
        <li key={i.key} className="grid grid-cols-[9rem_1fr_3rem] items-center gap-2">
          <span>{i.label}</span>
          <span className="bg-muted h-3 rounded">
            <span
              className="bg-primary block h-3 rounded"
              style={{ width: `${(i.value / max) * 100}%` }}
            />
          </span>
          <span className="text-right tabular-nums">{i.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function AnalyticsPage() {
  const { t, i18n } = useTranslation(["analytics", "enums", "common"]);
  const num = (n: number, d: number) =>
    n.toLocaleString(i18n.language, { minimumFractionDigits: d, maximumFractionDigits: d });
  const me = useMe();
  const search = route.useSearch();
  const navigate = route.useNavigate();
  const to = search.to ?? day(new Date());
  const from = search.from ?? day(new Date(Date.parse(to) - 6 * 86_400_000));
  const groupBy = search.group_by ?? "user";
  const tooLong = (Date.parse(to) - Date.parse(from)) / 86_400_000 >= MAX_DAYS || from > to;
  const q = useQuery({
    queryKey: ["analytics", from, to, groupBy],
    enabled: me.permissions.includes("analytics.read") && !tooLong,
    queryFn: async () =>
      (await unwrap(
        api.GET("/api/v1/analytics/summary", {
          params: { query: { from, to, group_by: groupBy } },
        }),
      )) as unknown as Summary,
  });
  if (!me.permissions.includes("analytics.read"))
    return (
      <p role="alert" className="p-6">
        {t("forbidden")}
      </p>
    );
  const preset = (days: number) =>
    void navigate({
      search: (p) => ({
        ...p,
        from: day(new Date(Date.now() - (days - 1) * 86_400_000)),
        to: day(new Date()),
      }),
      replace: true,
    });
  const s = q.data;
  return (
    <section className="mx-auto max-w-6xl space-y-5 p-6" aria-labelledby="an-h">
      <h1 id="an-h" className="font-display text-2xl font-bold">
        {t("common:nav.analytics")}
      </h1>
      <div className="flex flex-wrap items-end gap-2">
        <Button size="sm" variant="outline" onClick={() => preset(7)}>
          {t("last_days", { n: 7 })}
        </Button>
        <Button size="sm" variant="outline" onClick={() => preset(30)}>
          {t("last_days", { n: 30 })}
        </Button>
        <label className="text-sm">
          {t("from")}{" "}
          <Input
            type="date"
            className="h-8 w-40"
            value={from}
            onChange={(e) =>
              void navigate({
                search: (p) => ({ ...p, from: e.target.value || undefined }),
                replace: true,
              })
            }
          />
        </label>
        <label className="text-sm">
          {t("to")}{" "}
          <Input
            type="date"
            className="h-8 w-40"
            value={to}
            onChange={(e) =>
              void navigate({
                search: (p) => ({ ...p, to: e.target.value || undefined }),
                replace: true,
              })
            }
          />
        </label>
        <label className="text-sm">
          {t("group_by")}{" "}
          <select
            className="border-input h-8 rounded-md border bg-transparent px-2"
            value={groupBy}
            onChange={(e) =>
              void navigate({
                search: (p) => ({
                  ...p,
                  group_by: e.target.value === "user" ? undefined : (e.target.value as "day"),
                }),
                replace: true,
              })
            }
          >
            <option value="user">{t("by_user")}</option>
            <option value="day">{t("by_day")}</option>
          </select>
        </label>
      </div>
      {tooLong ? (
        <p role="alert" className="text-destructive text-sm">
          {t("too_long", { n: MAX_DAYS })}
        </p>
      ) : null}
      {s ? (
        <>
          <div className="grid gap-2 sm:grid-cols-3">
            {[
              ["useful", s.totals.useful_stories],
              ["hours", num(s.totals.active_hours, 1)],
              ["usph", s.totals.uspH === null ? "—" : num(s.totals.uspH, 2)],
            ].map(([k, v]) => (
              <div key={String(k)} className="rounded border p-3">
                <p className="text-muted-foreground text-xs">
                  {t(`tile.${k}`)}
                  <HelpTip text={t(`hints:analytics.${k}`)} />
                </p>
                <p
                  className="text-2xl tabular-nums"
                  title={k === "usph" && s.totals.uspH === null ? t("no_activity") : undefined}
                >
                  {v}
                </p>
              </div>
            ))}
            {/* ADR-004: стоимость AI скрыта, пока она равна нулю. */}
            {s.totals.ai_cost_usd > 0 ? (
              <div className="rounded border p-3">
                <p className="text-muted-foreground text-xs">{t("tile.cost")}</p>
                <p className="text-2xl">${s.totals.ai_cost_per_useful?.toFixed(3) ?? "—"}</p>
              </div>
            ) : null}
          </div>
          <p className="text-muted-foreground text-xs">{t("usph_formula")}</p>
          <AiLoad from={from} to={to} />
          <div className="grid gap-6 md:grid-cols-2">
            <div className="space-y-2">
              <h2 className="font-medium">{t("funnel")}</h2>
              <Bars
                label={t("funnel")}
                items={s.funnel.map((f) => ({
                  key: f.status,
                  label: t(`enums:EventStatus.${f.status}`),
                  value: f.count,
                }))}
              />
            </div>
            <div className="space-y-2">
              <h2 className="font-medium">{t("feed_funnel")}</h2>
              <Bars
                label={t("feed_funnel")}
                items={(["suggested", "taken", "published"] as const).map((k) => ({
                  key: k,
                  label: t(`feed_step.${k}`),
                  value: s.feed_funnel[k],
                }))}
              />
            </div>
            <div className="space-y-2">
              <h2 className="font-medium">{t("reject_reasons")}</h2>
              <Bars
                label={t("reject_reasons")}
                items={s.reject_reasons.map((r) => ({
                  key: r.reason,
                  label: t(`enums:RejectionReason.${r.reason}`),
                  value: r.count,
                }))}
              />
            </div>
            <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-sm">
              <dt>
                {t("tts")}
                <HelpTip text={t("hints:analytics.tts")} />
              </dt>
              <dd>
                {s.time_to_select_p50_min === null
                  ? "—"
                  : t("minutes", { n: Math.round(s.time_to_select_p50_min) })}
              </dd>
              <dt>
                {t("precision_high")}
                <HelpTip text={t("hints:analytics.precision")} />
              </dt>
              <dd>{pct(s.precision_high)}</dd>
              {Object.entries(s.precision_high_by_origin).map(([o, v]) => (
                <div key={o} className="contents">
                  <dt className="pl-3">
                    {t("by_origin", { origin: t(`origin.${o}`, { defaultValue: o }) })}
                  </dt>
                  <dd>{pct(v)}</dd>
                </div>
              ))}
              <dt>
                {t("edit_ratio")}
                <HelpTip text={t("hints:analytics.edit_ratio")} />
              </dt>
              <dd>{pct(s.draft_edit_ratio_p50)}</dd>
              {Object.entries(s.draft_edit_ratio_p50_by_origin).map(([o, v]) => (
                <div key={o} className="contents">
                  <dt className="pl-3">{t(`origin.${o}`, { defaultValue: o })}</dt>
                  <dd>{pct(v)}</dd>
                </div>
              ))}
            </dl>
          </div>
          <DataTable aria-label={t("usph_table")}>
            <thead>
              <tr>
                <th>{groupBy === "user" ? t("by_user") : t("by_day")}</th>
                <th>{t("tile.useful")}</th>
                <th>{t("tile.hours")}</th>
                <th>{t("usph_table")}</th>
              </tr>
            </thead>
            <tbody>
              {s.rows.map((r) => (
                <tr key={r.key}>
                  <td>{r.label}</td>
                  <td>{r.useful_stories}</td>
                  <td>{num(r.active_hours, 1)}</td>
                  <td title={r.uspH === null ? t("no_activity") : undefined}>
                    {r.uspH === null ? "—" : num(r.uspH, 2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
          {s.first_source_leaders.length ? (
            <div className="space-y-2">
              <h2 className="font-medium">
                {t("leaders")}
                <HelpTip text={t("hints:analytics.leaders")} />
              </h2>
              <Bars
                label={t("leaders")}
                items={s.first_source_leaders.map((l) => ({
                  key: l.source_id,
                  label: l.name,
                  value: l.useful_first_count,
                }))}
              />
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
