import { useTranslation } from "react-i18next";

import { useMe } from "@/entities/user";
import { useHotkey } from "@/shared/lib/hotkeys";
import { Button, Hint } from "@/shared/ui";

export function EditButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation(["event", "hints"]);
  const me = useMe();
  const allowed = me.permissions.includes("events.edit");
  useHotkey("e", onClick, { enabled: allowed && me.hotkeys_enabled });
  return allowed ? (
    <Hint text={t("hints:event.edit")}>
      <Button size="sm" variant="outline" aria-keyshortcuts="e" onClick={onClick}>
        {t("edit.edit")}
      </Button>
    </Hint>
  ) : null;
}
