import { useMutation, useQueryClient } from "@tanstack/react-query";

import { eventKeys } from "@/entities/event";
import { api, unwrap } from "@/shared/api";

import { normalizeUrlInput } from "./useAddUrl";

export const MAX_URLS = 10;

/** Строки «Links das fontes» → URL; null на месте невалидной строки. */
export function parseUrlLines(text: string): (string | null)[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean)
    .map(normalizeUrlInput);
}

export interface CreateEventBody {
  title: string;
  summary: string | null;
  sport_id: string | null;
  competition_id: string | null;
  team_ids: string[];
  player_ids: string[];
  urls: string[];
}

export function useCreateEvent() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ body, key }: { body: CreateEventBody; key: string }) =>
      unwrap(api.POST("/api/v1/events", { body, headers: { "Idempotency-Key": key } })),
    onSuccess: () => void qc.invalidateQueries({ queryKey: [...eventKeys.all, "list"] }),
  });
}
