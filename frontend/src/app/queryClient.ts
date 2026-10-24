import { QueryClient } from "@tanstack/react-query";

import { isAppError } from "@/shared/api";

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 15_000,
        // Повторяем только серверные сбои; 4xx — ошибка запроса, повтор не поможет.
        retry: (count, err) => (isAppError(err) && err.status >= 500 ? count < 3 : false),
        refetchOnWindowFocus: true,
      },
      mutations: { retry: 0 },
    },
  });
}
