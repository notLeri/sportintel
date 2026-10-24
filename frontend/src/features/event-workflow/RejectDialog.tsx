import { useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Label,
  Textarea,
} from "@/shared/ui";

const REASONS = [
  "DUPLICATE",
  "IRRELEVANT",
  "LOW_QUALITY",
  "INCORRECT",
  "OLD_NEWS",
  "NOT_TELEGRAM_WORTHY",
  "OTHER",
] as const;
const MAX = 500;

export function RejectDialog({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onConfirm: (reason: string, comment: string | null) => void;
}) {
  const { t } = useTranslation(["event", "enums"]);
  const [reason, setReason] = useState<string>("DUPLICATE");
  const [comment, setComment] = useState("");
  const invalid = (reason === "OTHER" && !comment.trim()) || comment.length > MAX;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("workflow.reject_title")}</DialogTitle>
        </DialogHeader>
        <form
          className="space-y-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!invalid) onConfirm(reason, comment.trim() || null);
          }}
        >
          <fieldset className="space-y-1">
            <legend className="text-sm font-medium">{t("workflow.reason")}</legend>
            {REASONS.map((r) => (
              <label key={r} className="flex items-center gap-2 text-sm">
                <input
                  type="radio"
                  name="reason"
                  value={r}
                  checked={reason === r}
                  onChange={() => setReason(r)}
                />
                {t(`enums:RejectionReason.${r}`)}
              </label>
            ))}
          </fieldset>
          <div className="space-y-1">
            <Label htmlFor="reject-comment">{t("workflow.comment")}</Label>
            <Textarea
              id="reject-comment"
              value={comment}
              maxLength={MAX}
              required={reason === "OTHER"}
              onChange={(e) => setComment(e.target.value)}
            />
            <p className="text-muted-foreground text-right text-xs" aria-live="polite">
              {comment.length}/{MAX}
            </p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("workflow.cancel")}
            </Button>
            <Button type="submit" variant="destructive" disabled={invalid}>
              {t("workflow.to.REJECTED")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
