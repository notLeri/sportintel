import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { EventDetail } from "@/entities/event";
import { useMe } from "@/entities/user";
import { useHotkey } from "@/shared/lib/hotkeys";
import { Button, Hint } from "@/shared/ui";

import { RejectDialog } from "./RejectDialog";
import { availableTransitions, HOTKEYS, labelKey } from "./transitionLabels";
import { useTransition } from "./useTransition";

/** Шаги утверждения — заливка цветом --ai палитры; отклонение — контур, красная заливка только в диалоге. */
const APPROVE = new Set(["SELECTED", "READY", "PUBLISHED"]);

export function WorkflowActions({
  event,
  onRejected,
}: {
  event: EventDetail;
  onRejected?: () => void;
}) {
  const { t } = useTranslation(["event", "hints"]);
  const me = useMe();
  const tr = useTransition(event.id);
  const [rejecting, setRejecting] = useState(false);
  const options = availableTransitions(me, event.status);
  const go = (to: string, reason?: string, comment?: string | null) =>
    tr.mutate(
      { to, reason, comment, version: event.version },
      { onSuccess: () => to === "REJECTED" && onRejected?.() },
    );
  const trigger = (to: string) => (to === "REJECTED" ? setRejecting(true) : go(to));
  const has = (to: string) => options.some((o) => o.to === to);
  useHotkey("t", () => has("REVIEWING") && trigger("REVIEWING"), { enabled: me.hotkeys_enabled });
  useHotkey("s", () => has("SELECTED") && trigger("SELECTED"), { enabled: me.hotkeys_enabled });
  useHotkey("r", () => has("REJECTED") && trigger("REJECTED"), { enabled: me.hotkeys_enabled });

  return (
    <div className="flex flex-wrap gap-1" role="group" aria-label={t("workflow.actions")}>
      {options.map((o) => {
        const approveBlocked = o.to === "READY" && event.draft?.state !== "ready";
        return (
          <Hint key={o.to} text={approveBlocked ? undefined : t(`hints:workflow.${o.to}`)}>
            <Button
              size="sm"
              variant={APPROVE.has(o.to) ? "ai" : "outline"}
              className={
                o.to === "REJECTED"
                  ? "text-destructive border-destructive hover:bg-destructive hover:text-white"
                  : undefined
              }
              disabled={tr.isPending || approveBlocked}
              title={approveBlocked ? t("workflow.approve_needs_draft") : undefined}
              aria-keyshortcuts={HOTKEYS[o.to]}
              onClick={() => trigger(o.to)}
            >
              {t(labelKey(event.status, o.to))}
            </Button>
          </Hint>
        );
      })}
      <RejectDialog
        open={rejecting}
        onOpenChange={setRejecting}
        onConfirm={(reason, comment) => {
          setRejecting(false);
          go("REJECTED", reason, comment);
        }}
      />
    </div>
  );
}
