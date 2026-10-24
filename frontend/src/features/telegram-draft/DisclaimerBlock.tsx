import { useTranslation } from "react-i18next";

import { HelpTip } from "@/shared/ui";

/** Статус проверки (не подтверждено / противоречия) — только редактору: в пост и в канал не попадает. */
export function DisclaimerBlock({ text }: { text: string | null }) {
  const { t } = useTranslation(["event", "hints"]);
  if (!text) return null;
  return (
    <div role="note" className="border-warn bg-warn-bg text-warn border p-2 text-sm">
      <p className="flex items-center text-xs font-semibold tracking-wide uppercase">
        {t("draft.editor_note")}
        <HelpTip text={t("hints:draft.disclaimer")} />
      </p>
      <p className="whitespace-pre-line">{text}</p>
    </div>
  );
}
