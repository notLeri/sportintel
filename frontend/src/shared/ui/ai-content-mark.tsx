import { SparklesIcon } from "lucide-react";
import { useTranslation } from "react-i18next";

import { cn } from "@/shared/lib/utils";

/** Маркер AI-контента (SRS §15): иконка + текст, не только цвет. Цвет — токен --ai палитры. */
export function AiContentMark({
  variant = "inline",
  reviewed = false,
}: {
  variant?: "inline" | "block";
  reviewed?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 text-xs font-medium",
        reviewed ? "text-ai-text border-ai-text border" : "bg-ai text-ai-foreground",
        variant === "block" && "mb-1 flex w-fit",
      )}
    >
      <SparklesIcon aria-hidden className="size-3" />
      {reviewed ? t("ai.reviewed") : t("ai.unreviewed")}
    </span>
  );
}
