import { useMe } from "./useMe";

export interface SystemStatus {
  ai: {
    mode: "rules" | "llm" | "mixed";
    llm: { configured: boolean; available: boolean; model: string | null };
  };
  sources_down: number;
  pipeline_delayed: boolean;
}

/** /me.system_status (BE-T4.14); null — сервер ещё не сообщил статус. */
export function useSystemStatus(): SystemStatus | null {
  return (useMe().system_status as SystemStatus | null) ?? null;
}
