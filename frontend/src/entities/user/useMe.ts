import { useSuspenseQuery } from "@tanstack/react-query";

import { meQuery } from "./queries";
import type { Me } from "./types";

/** Внутри защищённых маршрутов: данные гарантирует guard корневого маршрута. */
export function useMe(): Me {
  return useSuspenseQuery(meQuery).data;
}
