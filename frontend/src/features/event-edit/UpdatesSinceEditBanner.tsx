import { useTranslation } from "react-i18next";

import type { EventDetail } from "@/entities/event";
import { isAppError } from "@/shared/api";
import { Button, toast } from "@/shared/ui";

import { useRegenerateSummary } from "./useEditEvent";

/** «Новые источники после правки» (has_updates_since_edit) + перегенерация summary. */
export function UpdatesSinceEditBanner({ event }: { event: EventDetail }) {
  const { t } = useTranslation("event");
  const regen = useRegenerateSummary(event.id);
  if (!event.has_updates_since_edit) return null;
  return (
    <div
      role="status"
      className="flex flex-wrap items-center gap-2 bg-attention text-attention-foreground p-2 text-sm"
    >
      {t("edit.updates_since_edit")}
      <Button
        size="sm"
        variant="outline"
        disabled={regen.isPending}
        onClick={() =>
          regen.mutate(event.version, {
            onError: (e) => toast.error(isAppError(e) ? e.title : t("load_failed")),
          })
        }
      >
        {t("edit.regenerate_summary")}
      </Button>
    </div>
  );
}
