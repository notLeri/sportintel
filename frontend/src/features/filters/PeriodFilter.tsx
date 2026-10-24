import { useTranslation } from "react-i18next";

import { PERIODS, type Period } from "@/shared/lib/search";

import { useSearchParam } from "./useListSearchParam";

/** Период: значение по умолчанию (24h) в URL не пишется. */
export function PeriodFilter() {
  const { t } = useTranslation();
  const [period, setPeriod] = useSearchParam<Period>("period");
  return (
    <label className="flex items-center gap-2 text-sm">
      {t("filters.period")}
      <select
        className="border-input h-8 rounded-md border bg-transparent px-2"
        value={period ?? "24h"}
        onChange={(e) =>
          setPeriod(e.target.value === "24h" ? undefined : (e.target.value as Period))
        }
      >
        {PERIODS.filter((p) => p !== "custom").map((p) => (
          <option key={p} value={p}>
            {t(`filters.periods.${p}`)}
          </option>
        ))}
      </select>
    </label>
  );
}
