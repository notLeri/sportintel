import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api, unwrap } from "@/shared/api";

import { userKeys } from "./queries";

/** Сменить часовой пояс профиля: всё время в интерфейсе пересчитывается сразу. */
export function useSetTimeZone() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (timezone: string) => unwrap(api.PATCH("/api/v1/me", { body: { timezone } })),
    onSuccess: (me) => {
      qc.setQueryData(userKeys.me(), (old: object | undefined) => ({ ...old, ...me }));
      void qc.invalidateQueries();
    },
  });
}
