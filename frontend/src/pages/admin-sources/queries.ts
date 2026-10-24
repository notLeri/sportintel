import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { sourceKeys } from "@/entities/source";
import { api, unwrap } from "@/shared/api";

export const adminSourceKeys = {
  list: () => [...sourceKeys.all, "admin"] as const,
  detail: (id: string) => [...sourceKeys.all, "detail", id] as const,
  runs: (id: string) => [...sourceKeys.all, "runs", id] as const,
};

export function useAdminSources() {
  return useQuery({
    queryKey: adminSourceKeys.list(),
    queryFn: async () =>
      (await unwrap(api.GET("/api/v1/sources", { params: { query: { view: "admin" } } }))) as {
        items: AdminItem[];
      },
  });
}

export type AdminItem = import("@/shared/api").components["schemas"]["SourceAdminItem"];
export type SourceDetail = import("@/shared/api").components["schemas"]["SourceDetail"];
export type SourceCreate = import("@/shared/api").components["schemas"]["SourceCreate"];

export function usePatchSource(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ patch, version }: { patch: Record<string, unknown>; version: number }) =>
      unwrap(
        api.PATCH("/api/v1/sources/{source_id}", {
          params: { path: { source_id: id } },
          body: patch,
          headers: { "If-Match": `"${version}"` },
        }),
      ),
    onSuccess: (d) => {
      qc.setQueryData(adminSourceKeys.detail(id), d);
      void qc.invalidateQueries({ queryKey: sourceKeys.all });
    },
  });
}
