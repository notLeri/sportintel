import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, isAppError, unwrap, type components } from "@/shared/api";
import { formatDuration } from "@/shared/lib/datetime";
import { cn } from "@/shared/lib/utils";
import { Button, DataTable, HelpTip, Hint, Progress, toast } from "@/shared/ui";

type Load = components["schemas"]["AiLoad"];
type Advice = Load["advice"][number];

const pct = (v: number) => `${Math.round(v * 100)}%`;
const TONE: Record<Load["verdict"], string> = {
  ok: "border-success/40 bg-success/5",
  tight: "border-warn/50 bg-warn-bg",
  overloaded: "border-destructive/50 bg-destructive/5",
  failing: "border-destructive/50 bg-destructive/5",
  off: "",
};

/** «Нагрузка ИИ»: справляется ли модель с потоком событий при этих настройках и что
 * поменять, если нет. Советы с «Применить» меняют одну настройку. */
export function AiLoad({ from, to }: { from: string; to: string }) {
  const { t } = useTranslation(["analytics", "hints"]);
  const me = useMe();
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["analytics", "ai-load", from, to],
    queryFn: () =>
      unwrap(api.GET("/api/v1/analytics/ai-load", { params: { query: { from, to } } })),
  });
  const apply = useMutation({
    // PUT заменяет значение целиком: берём текущее и меняем одно поле
    mutationFn: async ({ key, field, value }: { key: string; field: string; value: unknown }) => {
      const cur = await unwrap(api.GET("/api/v1/settings/{key}", { params: { path: { key } } }));
      return unwrap(
        api.PUT("/api/v1/settings/{key}", {
          params: { path: { key } },
          body: { value: { ...cur.value, [field]: value } },
        }),
      );
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["analytics", "ai-load"] });
      void qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(t("ai_load.applied"));
    },
    onError: (e) => toast.error(isAppError(e) ? e.title : t("ai_load.apply_failed")),
  });
  const s = q.data;
  if (!s) return null;
  const canApply = me.permissions.includes("settings.manage");
  const important = (s.events_per_day.HIGH ?? 0) + (s.events_per_day.MEDIUM ?? 0);
  const perSource = s.sources ? important / s.sources : 0;
  const posts = s.backlog.post ?? 0;
  const translations = s.backlog.translate ?? 0;

  return (
    <section aria-labelledby="ai-load-h" className="space-y-3">
      <h2 id="ai-load-h" className="font-medium">
        {t("ai_load.title")}
        <HelpTip text={t("hints:analytics.ai_load")} />
      </h2>
      <div className={cn("space-y-2 rounded border p-3", TONE[s.verdict])}>
        <p className="font-medium">{t(`ai_load.verdict.${s.verdict}`)}</p>
        {s.verdict !== "off" ? (
          <>
            <div className="flex justify-between gap-2 text-xs">
              <span>
                {t("ai_load.share", { share: pct(s.share) })}
                <HelpTip text={t("hints:analytics.ai_share")} />
              </span>
              <span className="text-muted-foreground">
                {t("ai_load.busy", { share: pct(s.busy_share) })}
              </span>
            </div>
            <Progress value={s.share > 1 ? null : s.share} label={t("ai_load.share_label")} />
          </>
        ) : null}
        <p className="text-sm">
          {t("ai_load.flow", {
            important: Math.round(important),
            high: Math.round(s.events_per_day.HIGH ?? 0),
            medium: Math.round(s.events_per_day.MEDIUM ?? 0),
            sources: s.sources,
          })}
        </p>
        {posts + translations ? (
          <p className="text-sm">
            {t("ai_load.backlog", {
              posts,
              translations,
              eta: formatDuration(s.backlog_eta_s),
            })}
          </p>
        ) : null}
        {s.verdict === "ok" && s.headroom_events_per_day > 0 ? (
          <p className="text-muted-foreground text-sm">
            {t("ai_load.headroom", {
              events: s.headroom_events_per_day,
              sources: perSource ? Math.floor(s.headroom_events_per_day / perSource) : 0,
            })}
          </p>
        ) : null}
      </div>
      {s.kinds.length ? (
        <DataTable aria-label={t("ai_load.kinds")}>
          <thead>
            <tr>
              <th>{t("ai_load.kind")}</th>
              <th>{t("ai_load.calls")}</th>
              <th>{t("ai_load.failed")}</th>
              <th>{t("ai_load.typical")}</th>
              <th>{t("ai_load.model_time")}</th>
            </tr>
          </thead>
          <tbody>
            {s.kinds.map((k) => (
              <tr key={k.kind}>
                <td>{t(`ai_load.kind_name.${k.kind}`, { defaultValue: k.kind })}</td>
                <td>{k.calls}</td>
                <td>{k.failed}</td>
                <td>{k.p50_s === null ? "—" : formatDuration(k.p50_s)}</td>
                <td>{formatDuration(k.busy_s)}</td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      ) : null}
      {s.advice.length ? (
        <div className="space-y-2">
          <h3 className="text-sm font-medium">{t("ai_load.advice_title")}</h3>
          <ul className="space-y-2">
            {s.advice.map((a) => (
              <AdviceRow
                key={`${a.id}-${String(a.params.source_id ?? "")}`}
                a={a}
                canApply={canApply}
                applying={apply.isPending}
                onApply={() => a.apply && apply.mutate(a.apply as never)}
              />
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

function AdviceRow({
  a,
  canApply,
  applying,
  onApply,
}: {
  a: Advice;
  canApply: boolean;
  applying: boolean;
  onApply: () => void;
}) {
  const { t } = useTranslation(["analytics", "hints"]);
  const p = a.params as Record<string, string | number>;
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 rounded border p-2 text-sm">
      <div className="min-w-0 space-y-0.5">
        <p>{t(`ai_load.advice.${a.id}`, p)}</p>
        {a.share_after !== null ? (
          <p className="text-muted-foreground text-xs">
            {t("ai_load.share_after", { share: pct(a.share_after) })}
          </p>
        ) : null}
      </div>
      {a.apply ? (
        <Hint text={canApply ? t("hints:analytics.ai_apply") : t("ai_load.need_settings")}>
          <span>
            <Button size="sm" variant="outline" disabled={!canApply || applying} onClick={onApply}>
              {t("ai_load.apply")}
            </Button>
          </span>
        </Hint>
      ) : a.id === "noisy_source" ? (
        <Button size="sm" variant="ghost" asChild>
          <Link to="/admin/sources/$sourceId" params={{ sourceId: String(p.source_id) }}>
            {t("ai_load.open_source")}
          </Link>
        </Button>
      ) : (
        <Button size="sm" variant="ghost" asChild>
          <Link to="/admin/settings">{t("ai_load.open_settings")}</Link>
        </Button>
      )}
    </li>
  );
}
