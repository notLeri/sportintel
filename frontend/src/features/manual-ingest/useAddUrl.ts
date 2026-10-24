import { useMutation, useQueryClient } from "@tanstack/react-query";

import { articleKeys } from "@/entities/article";
import { api, unwrap } from "@/shared/api";

export function normalizeUrlInput(raw: string): string | null {
  const value = raw.trim();
  if (!value) return null;
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(value) ? value : `https://${value}`;
  try {
    const url = new URL(withScheme);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

export function useAddUrl() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ url, key }: { url: string; key: string }) =>
      unwrap(api.POST("/api/v1/articles", { body: { url }, headers: { "Idempotency-Key": key } })),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: articleKeys.all }),
  });
}
