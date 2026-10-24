import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { type DraftDetail, draftVersionQuery, TelegramPreview } from "@/entities/draft";
import { formatDateTime } from "@/shared/lib/datetime";
import { Button } from "@/shared/ui";

export function VersionHistory({
  draft,
  timeZone,
  onRestore,
}: {
  draft: DraftDetail;
  timeZone: string;
  onRestore: (tgHtml: string) => void;
}) {
  const { t } = useTranslation(["event", "enums"]);
  const [open, setOpen] = useState<number | null>(null);
  const v = useQuery({ ...draftVersionQuery(draft.id, open ?? 0), enabled: open !== null });
  return (
    <section aria-label={t("draft_panel.history")} className="space-y-2 text-sm">
      <ul className="space-y-1">
        {draft.versions.map((x) => (
          <li key={x.n}>
            <button
              type="button"
              className="hover:underline"
              aria-pressed={open === x.n}
              onClick={() => setOpen(x.n)}
            >
              v{x.n} · {x.lang} · {t(`enums:TextOrigin.${x.origin}`)} ·{" "}
              {formatDateTime(x.created_at, timeZone)}
            </button>
          </li>
        ))}
      </ul>
      {open !== null && v.data ? (
        <div className="space-y-2">
          <TelegramPreview
            tgHtml={v.data.body_tg_html}
            imageUrl={v.data.image_url}
            channelName={`v${v.data.n}`}
          />
          <Button size="sm" variant="outline" onClick={() => onRestore(v.data.body_tg_html)}>
            {t("draft_panel.restore_version")}
          </Button>
        </div>
      ) : null}
    </section>
  );
}
