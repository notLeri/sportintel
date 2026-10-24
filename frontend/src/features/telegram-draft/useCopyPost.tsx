import * as Sentry from "@sentry/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { api } from "@/shared/api";
import { buildClipboard } from "@/shared/lib/telegram";
import { Dialog, DialogContent, DialogHeader, DialogTitle, Textarea, toast } from "@/shared/ui";

export interface CopySource {
  draftId: string;
  versionN: number;
  tgHtml: string;
}

/**
 * Копирование поста (FE-T3.13): text/html + text/plain. clipboard.write вызывается синхронно из жеста
 * пользователя — без await до вызова (§22).
 */
export function useCopyPost() {
  const { t } = useTranslation("common");
  const [manual, setManual] = useState<string | null>(null);
  const copy = (src: CopySource) => {
    const { html, plain } = buildClipboard(src.tgHtml);
    const write =
      typeof ClipboardItem !== "undefined" && navigator.clipboard?.write
        ? navigator.clipboard.write([
            new ClipboardItem({
              "text/html": new Blob([html], { type: "text/html" }),
              "text/plain": new Blob([plain], { type: "text/plain" }),
            }),
          ])
        : navigator.clipboard?.writeText
          ? navigator.clipboard.writeText(plain)
          : Promise.reject(new Error("clipboard unavailable"));
    write.then(
      () => {
        toast.success(t("telegram.copied"));
        api
          .POST("/api/v1/drafts/{draft_id}:copied", {
            params: { path: { draft_id: src.draftId } },
            body: { version_n: src.versionN },
          })
          .catch((e: unknown) => Sentry.captureException(e));
      },
      () => setManual(plain),
    );
  };
  const fallback = (
    <Dialog open={manual !== null} onOpenChange={(o) => !o && setManual(null)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("telegram.copy_manual")}</DialogTitle>
        </DialogHeader>
        <Textarea
          readOnly
          rows={10}
          value={manual ?? ""}
          onFocus={(e) => e.currentTarget.select()}
        />
      </DialogContent>
    </Dialog>
  );
  return { copy, fallback };
}
