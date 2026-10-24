import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { api, unwrap } from "@/shared/api";
import { formatDateTime } from "@/shared/lib/datetime";
import { cn } from "@/shared/lib/utils";
import { Button, Checkbox, DataTable, HelpTip, toast } from "@/shared/ui";

const STALL_S = 15 * 60;
const keys = {
  summary: ["pipeline", "summary"] as const,
  failures: (kind: string, code?: string) => ["pipeline", "failures", kind, code ?? null] as const,
};

export function PipelinePage() {
  const { t } = useTranslation(["admin", "hints"]);
  const me = useMe();
  const qc = useQueryClient();
  const [tab, setTab] = useState<"articles" | "jobs">("articles");
  const [code, setCode] = useState<string | undefined>();
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const allowed = me.permissions.includes("pipeline.manage");
  const summary = useQuery({
    queryKey: keys.summary,
    enabled: allowed,
    refetchInterval: 30_000,
    queryFn: () => unwrap(api.GET("/api/v1/pipeline/summary")),
  });
  const failures = useQuery({
    queryKey: keys.failures(tab, code),
    enabled: allowed,
    refetchInterval: 30_000,
    queryFn: () =>
      unwrap(api.GET("/api/v1/pipeline/failures", { params: { query: { kind: tab, code } } })),
  });
  const retry = useMutation({
    mutationFn: (body: { article_ids?: string[]; failure_code?: string; job_ids?: number[] }) =>
      unwrap(api.POST("/api/v1/pipeline/failures:retry", { body })),
    onSuccess: (r) => {
      setSelected(new Set());
      void qc.invalidateQueries({ queryKey: ["pipeline"] });
      toast.success(
        r.remaining
          ? t("pipeline.retried_rest", { n: r.retried, rest: r.remaining })
          : t("pipeline.retried", { n: r.retried }),
      );
    },
  });
  if (!allowed) return <p role="alert">{t("forbidden")}</p>;
  const s = summary.data;
  const toggle = (id: string) =>
    setSelected((p) => {
      const n = new Set(p);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  return (
    <section aria-labelledby="pipe-h" className="space-y-4">
      <h2 id="pipe-h" className="text-lg font-semibold">
        {t("section.pipeline")}
      </h2>
      {s ? (
        <div className="grid gap-3 sm:grid-cols-3">
          <div className="bg-card rounded-lg border p-4">
            <h3 className="text-muted-foreground text-xs font-semibold">
              {t("pipeline.articles_24h")}
            </h3>
            <dl className="mt-2 grid grid-cols-[1fr_auto] gap-y-1 text-sm tabular-nums">
              {Object.entries(s.articles_24h).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt>{t(`pipeline.state.${k}`)}</dt>
                  <dd className="text-right font-semibold">{v}</dd>
                </div>
              ))}
            </dl>
          </div>
          <div className="bg-card rounded-lg border p-4 text-sm">
            <h3 className="text-muted-foreground flex items-center text-xs font-semibold">
              {t("pipeline.lag")}
              <HelpTip text={t("hints:pipeline.lag")} />
            </h3>
            <p className="font-display mt-2 text-3xl font-bold tabular-nums">
              {s.ingest_lag_p95_s === null ? "—" : Math.round(s.ingest_lag_p95_s / 60)}
            </p>
          </div>
          <div className="bg-card rounded-lg border p-4 text-sm">
            <h3 className="text-muted-foreground text-xs font-semibold">
              {t("pipeline.drafts_failed")}
            </h3>
            <p className="font-display mt-2 text-3xl font-bold tabular-nums">
              {s.drafts_failed_24h}
            </p>
          </div>
        </div>
      ) : null}
      {s ? (
        <DataTable aria-label={t("pipeline.queues")}>
          <thead>
            <tr>
              <th>
                <span className="inline-flex items-center">
                  {t("pipeline.queue")}
                  <HelpTip text={t("hints:pipeline.queues")} />
                </span>
              </th>
              <th className="shrink num">{t("pipeline.todo")}</th>
              <th className="shrink num">{t("pipeline.doing")}</th>
              <th className="shrink num">{t("pipeline.failed_24h")}</th>
              <th className="shrink num">{t("pipeline.oldest")}</th>
            </tr>
          </thead>
          <tbody>
            {s.queues.map((q) => {
              const stalled = (q.oldest_todo_age_s ?? 0) > STALL_S;
              return (
                <tr
                  key={q.queue}
                  className={cn(stalled && "bg-destructive/10 text-destructive")}
                  data-stalled={stalled}
                >
                  <td>{t(`pipeline.queue_names.${q.queue}`, { defaultValue: q.queue })}</td>
                  <td className="num">{q.todo}</td>
                  <td className="num">{q.doing}</td>
                  <td className={cn("num", q.failed_24h > 0 && "text-warn font-semibold")}>
                    {q.failed_24h}
                  </td>
                  <td className="shrink num">
                    {q.oldest_todo_age_s === null
                      ? "—"
                      : `${Math.round(q.oldest_todo_age_s / 60)} min`}
                    {stalled ? ` · ${t("pipeline.stalled")}` : ""}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </DataTable>
      ) : null}
      <div role="tablist" className="flex gap-1">
        {(["articles", "jobs"] as const).map((k) => (
          <Button
            key={k}
            role="tab"
            size="sm"
            aria-selected={tab === k}
            variant={tab === k ? "default" : "outline"}
            onClick={() => {
              setTab(k);
              setSelected(new Set());
            }}
          >
            {t(`pipeline.tab.${k}`)}
          </Button>
        ))}
      </div>
      {tab === "articles" ? (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-sm">
              {t("pipeline.code")}{" "}
              <select
                className="border-input h-8 rounded-md border bg-transparent px-2"
                value={code ?? ""}
                onChange={(e) => setCode(e.target.value || undefined)}
              >
                <option value="">—</option>
                {(s?.failures_by_code ?? []).map((c) => (
                  <option key={c.code ?? ""} value={c.code ?? ""}>
                    {c.code} ({c.count})
                  </option>
                ))}
              </select>
            </label>
            <Button
              size="sm"
              disabled={!selected.size || retry.isPending}
              onClick={() => retry.mutate({ article_ids: [...selected] })}
            >
              {t("pipeline.retry_selected")}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={!code || retry.isPending}
              onClick={() => code && retry.mutate({ failure_code: code })}
            >
              {t("pipeline.retry_code")}
            </Button>
          </div>
          <DataTable>
            <thead>
              <tr>
                <th className="shrink" />
                <th>{t("pipeline.title")}</th>
                <th className="shrink">{t("pipeline.source")}</th>
                <th className="shrink">{t("pipeline.code")}</th>
                <th className="shrink">{t("pipeline.when")}</th>
              </tr>
            </thead>
            <tbody>
              {failures.data && !failures.data.articles.length ? (
                <tr>
                  <td colSpan={5} className="text-muted-foreground py-8! text-center">
                    {t("pipeline.empty_articles")}
                  </td>
                </tr>
              ) : null}
              {(failures.data?.articles ?? []).map((a) => (
                <tr key={a.id}>
                  <td className="shrink">
                    <Checkbox
                      aria-label={t("pipeline.select", { title: a.title })}
                      checked={selected.has(a.id)}
                      onCheckedChange={() => toggle(a.id)}
                    />
                  </td>
                  <td>
                    <a
                      href={a.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="hover:underline"
                    >
                      {a.title}
                    </a>
                  </td>
                  <td className="shrink">{a.source_name}</td>
                  <td className="shrink font-mono text-xs" title={a.failure_detail ?? undefined}>
                    {a.failure_code}
                  </td>
                  <td className="shrink text-muted-foreground">
                    {formatDateTime(a.state_changed_at, me.timezone)}
                  </td>
                </tr>
              ))}
            </tbody>
          </DataTable>
        </div>
      ) : (
        <DataTable>
          <thead>
            <tr>
              <th>{t("pipeline.task")}</th>
              <th>{t("pipeline.queue")}</th>
              <th className="shrink num">{t("pipeline.attempts")}</th>
              <th className="shrink" />
            </tr>
          </thead>
          <tbody>
            {failures.data && !failures.data.jobs.length ? (
              <tr>
                <td colSpan={4} className="text-muted-foreground py-8! text-center">
                  {t("pipeline.empty_jobs")}
                </td>
              </tr>
            ) : null}
            {(failures.data?.jobs ?? []).map((j) => (
              <tr key={j.id}>
                <td>{j.task_name}</td>
                <td>{t(`pipeline.queue_names.${j.queue}`, { defaultValue: j.queue })}</td>
                <td className="num">{j.attempts}</td>
                <td className="shrink">
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => retry.mutate({ job_ids: [j.id] })}
                  >
                    {t("pipeline.retry_job")}
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </DataTable>
      )}
    </section>
  );
}
