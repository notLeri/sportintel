import { useNavigate, useSearch } from "@tanstack/react-router";
import { useCallback } from "react";

type AnySearch = Record<string, unknown>;

/** Search param как источник состояния фильтра (URL — закладка, CONV §11.1). */
export function useSearchParam<T>(name: string): [T | undefined, (value: T | undefined) => void] {
  const search = useSearch({ strict: false }) as AnySearch;
  const navigate = useNavigate();
  const set = useCallback(
    (value: T | undefined) => {
      void navigate({
        to: ".",
        search: ((prev: AnySearch) => ({ ...prev, [name]: value, cursor: undefined })) as never,
        replace: true,
      });
    },
    [name, navigate],
  );
  return [search[name] as T | undefined, set];
}

export function useListSearchParam(name: string): [string[], (values: string[]) => void] {
  const [value, set] = useSearchParam<string[]>(name);
  const setList = useCallback((values: string[]) => set(values.length ? values : undefined), [set]);
  return [value ?? [], setList];
}
