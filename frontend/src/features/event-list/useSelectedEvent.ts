import { getRouteApi } from "@tanstack/react-router";
import { useCallback } from "react";

const route = getRouteApi("/");

/** Выбранное событие — `?event=` (CONV §11.1). */
export function useSelectedEvent(): [string | undefined, (id: string | undefined) => void] {
  const { event } = route.useSearch();
  const navigate = route.useNavigate();
  const select = useCallback(
    (id: string | undefined) =>
      void navigate({ search: (prev) => ({ ...prev, event: id }), replace: true }),
    [navigate],
  );
  return [event, select];
}
