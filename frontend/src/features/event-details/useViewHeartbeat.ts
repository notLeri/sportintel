import { useEffect } from "react";

import { api } from "@/shared/api";

const EVERY_MS = 60_000;

/** Heartbeat просмотра (FE-T4.15): сразу и раз в минуту, только при видимой вкладке; ошибки игнорируются. */
export function useViewHeartbeat(eventId: string | undefined) {
  useEffect(() => {
    if (!eventId) return;
    const beat = () => {
      if (document.visibilityState === "visible")
        void api
          .POST("/api/v1/analytics/heartbeat", { body: { event_id: eventId } })
          .catch(() => undefined);
    };
    beat();
    const id = setInterval(beat, EVERY_MS);
    return () => clearInterval(id);
  }, [eventId]);
}
