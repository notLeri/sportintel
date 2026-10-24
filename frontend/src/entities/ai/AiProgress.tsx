import { useTranslation } from "react-i18next";

import { formatDuration } from "@/shared/lib/datetime";
import { HelpTip, Progress } from "@/shared/ui";

import { type AiKind, useAiProgress, useElapsed } from "./queries";

// Пока замеров нет (как на сервере, platform/ai_usage.DEFAULT_S)
const DEFAULT_S: Record<AiKind, number> = {
  post: 50,
  rewrite: 50,
  translate: 20,
  translate_post: 15,
  brief: 45,
};

/** Одна работа ИИ: сколько прошло из обычного. Дольше обычного — бегущая полоса. */
function AiBar({ label, elapsed, typical }: { label: string; elapsed: number; typical: number }) {
  const { t } = useTranslation("common");
  const over = elapsed > typical;
  const args = { elapsed: formatDuration(elapsed), typical: formatDuration(typical) };
  return (
    <div className="space-y-1 text-xs">
      <div className="flex items-baseline justify-between gap-2">
        <span className="min-w-0 truncate">{label}</span>
        <span className="text-muted-foreground shrink-0 tabular-nums">
          {over ? t("ai.longer", args) : t("ai.elapsed", args)}
        </span>
      </div>
      <Progress value={over ? null : Math.min(elapsed / typical, 0.95)} label={label} />
    </div>
  );
}

/** Прогресс своего запроса к ИИ («Переписать», «Перевести»): ответ придёт целиком, а пока —
 * сколько прошло из обычного времени такой работы. */
export function AiWait({ kind, active }: { kind: AiKind; active: boolean }) {
  const { t } = useTranslation("common");
  const q = useAiProgress(active);
  const elapsed = useElapsed(active);
  if (!active) return null;
  return (
    <AiBar
      label={t(`ai.wait.${kind}`)}
      elapsed={elapsed}
      typical={q.data?.typical_s[kind] ?? DEFAULT_S[kind]}
    />
  );
}

/** ИИ прямо сейчас работает над этим событием (фоновая задача): что именно и сколько ждать. */
export function AiEventStatus({ eventId, kinds }: { eventId: string; kinds: AiKind[] }) {
  const { t } = useTranslation("common");
  const q = useAiProgress();
  const since = useElapsed(Boolean(q.data?.running.length), q.dataUpdatedAt);
  const runs = (q.data?.running ?? []).filter(
    (r) => r.event_id === eventId && kinds.includes(r.kind as AiKind),
  );
  if (!runs.length) return null;
  return (
    <div className="space-y-2">
      {runs.map((r) => (
        <AiBar
          key={r.kind}
          label={t(`ai.now.${r.kind}`)}
          elapsed={r.elapsed_s + since}
          typical={r.typical_s}
        />
      ))}
    </div>
  );
}

/** Очереди ИИ: что пишется сейчас, сколько ждут и когда разойдётся. Пусто — ничего не показывает. */
export function AiQueuePanel({ kinds }: { kinds: AiKind[] }) {
  const { t } = useTranslation(["common", "hints"]);
  const q = useAiProgress();
  const since = useElapsed(Boolean(q.data?.running.length), q.dataUpdatedAt);
  const p = q.data;
  const running = (p?.running ?? []).filter((r) => kinds.includes(r.kind as AiKind));
  const queues = (p?.queues ?? []).filter((x) => kinds.includes(x.kind) && x.pending > 0);
  if (!running.length && !queues.length) return null;
  return (
    <section
      aria-label={t("ai.title")}
      className="bg-muted/30 space-y-3 rounded-md border p-3 text-sm"
    >
      <h2 className="text-xs font-medium">
        {t("ai.title")}
        <HelpTip text={t("hints:ai.queue")} />
      </h2>
      {running.map((r) => (
        <AiBar
          key={`${r.kind}-${r.event_id ?? ""}`}
          label={r.title ? t(`ai.writing.${r.kind}`, { title: r.title }) : t(`ai.now.${r.kind}`)}
          elapsed={r.elapsed_s + since}
          typical={r.typical_s}
        />
      ))}
      {queues.map((x) => {
        const total = x.done_24h + x.pending;
        return (
          <div key={x.kind} className="space-y-1 text-xs">
            <div className="flex items-baseline justify-between gap-2">
              <span>{t(`ai.queue.${x.kind}`, { count: x.pending })}</span>
              <span className="text-muted-foreground shrink-0 tabular-nums">
                {t("ai.eta", { eta: formatDuration(x.eta_s) })}
              </span>
            </div>
            <Progress
              value={total ? x.done_24h / total : 0}
              label={t("ai.done_of", { done: x.done_24h, total })}
            />
            <p className="text-muted-foreground flex justify-between gap-2">
              <span className="min-w-0 truncate">
                {x.next.length
                  ? t("ai.next", { titles: x.next.map((n) => `«${n.title}»`).join(" · ") })
                  : null}
              </span>
              <span className="shrink-0">{t("ai.done_of", { done: x.done_24h, total })}</span>
            </p>
          </div>
        );
      })}
    </section>
  );
}
