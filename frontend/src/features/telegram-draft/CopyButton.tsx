import { useTranslation } from "react-i18next";

import { Button, Hint } from "@/shared/ui";

import { type CopySource, useCopyPost } from "./useCopyPost";

export function CopyButton({
  source,
  disabled,
}: {
  source: CopySource | null;
  disabled?: boolean;
}) {
  const { t } = useTranslation(["common", "hints"]);
  const { copy, fallback } = useCopyPost();
  return (
    <>
      <Hint text={t("hints:draft.copy")}>
        <Button
          size="sm"
          variant="outline"
          disabled={disabled || !source}
          aria-keyshortcuts="c"
          onClick={() => source && copy(source)}
        >
          {t("telegram.copy")}
        </Button>
      </Hint>
      {fallback}
    </>
  );
}
