import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Input } from "@/shared/ui";

import { useSearchParam } from "./useListSearchParam";

export const SEARCH_DEBOUNCE_MS = 300;

export function SearchInput() {
  const { t } = useTranslation();
  const [q, setQ] = useSearchParam<string>("q");
  const [value, setValue] = useState(q ?? "");

  useEffect(() => setValue(q ?? ""), [q]);
  useEffect(() => {
    if ((q ?? "") === value) return;
    const id = setTimeout(() => setQ(value.trim() || undefined), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [value, q, setQ]);

  return (
    <Input
      type="search"
      aria-label={t("filters.search")}
      placeholder={t("filters.search")}
      className="h-8 w-64"
      value={value}
      onChange={(e) => setValue(e.target.value)}
    />
  );
}
