import { useTranslation } from "react-i18next";

import { StatusDot, type StatusTone } from "@/shared/ui";

// Путь статьи: найдена → текст получен → проанализирована (синие — в работе) → в событии (зелёная).
const TONE: Record<string, StatusTone> = {
  failed: "danger",
  discovered: "neutral",
  extracted: "info",
  enriched: "info",
  clustered: "success",
};

export function ArticleStateBadge({
  state,
  failureCode,
}: {
  state: string;
  failureCode?: string | null;
}) {
  const { t } = useTranslation("enums");
  const label = t(`ArticleState.${state}`, { defaultValue: state });
  const reason = failureCode
    ? t(`FailureCode.${failureCode}`, { defaultValue: failureCode })
    : null;
  return (
    <StatusDot tone={TONE[state] ?? "neutral"} title={reason ?? undefined}>
      {reason ? `${label}: ${reason}` : label}
    </StatusDot>
  );
}
