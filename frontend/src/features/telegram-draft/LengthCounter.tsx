import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/utils";

export function LengthCounter({ length, max }: { length: number; max: number }) {
  const { t } = useTranslation("event");
  const over = length > max;
  return (
    <span
      aria-live="polite"
      className={cn(
        "text-xs tabular-nums",
        over ? "text-destructive font-semibold" : "text-muted-foreground",
      )}
    >
      {length} / {max}
      {over ? ` · ${t("draft_panel.too_long")}` : ""}
    </span>
  );
}
