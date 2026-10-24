import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { api, unwrap, type components } from "@/shared/api";

export type AiProgress = components["schemas"]["AiProgress"];
export type AiKind = "post" | "rewrite" | "translate" | "translate_post" | "brief";

export const aiProgressKey = ["ai-progress"] as const;

const busy = (p: AiProgress | undefined) =>
  Boolean(p && (p.running.length || p.queues.some((q) => q.pending > 0)));

/** Что ИИ делает сейчас и сколько ждут очереди. Пока ИИ занят — опрос каждые 5 с. */
export function useAiProgress(enabled = true) {
  return useQuery({
    queryKey: aiProgressKey,
    enabled,
    queryFn: () => unwrap(api.GET("/api/v1/ai/progress")),
    refetchInterval: (q) => (busy(q.state.data) ? 5_000 : 30_000),
    refetchIntervalInBackground: false,
  });
}

/** Секунды с момента start (или с включения active), обновляются раз в секунду. */
export function useElapsed(active: boolean, start?: number): number {
  const [now, setNow] = useState(() => Date.now());
  const [from, setFrom] = useState(() => start ?? Date.now());
  useEffect(() => {
    if (!active) return;
    setFrom(start ?? Date.now());
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(id);
  }, [active, start]);
  return active ? Math.max(0, (now - from) / 1_000) : 0;
}
