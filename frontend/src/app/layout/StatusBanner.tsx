import { Link } from "@tanstack/react-router";
import { InfoIcon, TriangleAlertIcon, XIcon } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useMe, useSystemStatus } from "@/entities/user";
import { cn } from "@/shared/lib/utils";

const KEY = "status-banner-dismissed";

function readDismissed(): string | null {
  try {
    return sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

/** Баннер системного статуса (FE-T4.14). Закрытие действует до следующего изменения статуса. */
export function StatusBanner() {
  const { t } = useTranslation("common");
  const me = useMe();
  const s = useSystemStatus();
  const [dismissed, setDismissed] = useState(readDismissed);
  if (!s) return null;
  const notes: { text: string; warn: boolean; link?: boolean }[] = [];
  // ADR-004: недоступная LM — информация, конвейер работает на правилах.
  if (s.ai.llm.configured && !s.ai.llm.available)
    notes.push({ text: t("status.llm_offline"), warn: false });
  if (s.sources_down > 0)
    notes.push({
      text: t("status.sources_down", { count: s.sources_down }),
      warn: true,
      link: me.permissions.includes("sources.manage"),
    });
  if (s.pipeline_delayed) notes.push({ text: t("status.pipeline_delayed"), warn: true });
  const signature = JSON.stringify(notes.map((n) => n.text));
  if (!notes.length || dismissed === signature) return null;
  const warn = notes.some((n) => n.warn);
  return (
    <div
      role="status"
      className={cn(
        "flex flex-wrap items-center gap-3 px-4 py-2 text-sm",
        warn ? "bg-attention text-attention-foreground" : "bg-muted text-foreground",
      )}
    >
      {warn ? (
        <TriangleAlertIcon aria-hidden className="size-4 shrink-0" />
      ) : (
        <InfoIcon aria-hidden className="size-4 shrink-0" />
      )}
      {notes.map((n) => (
        <span key={n.text}>
          {n.text}
          {n.link ? (
            <>
              {" "}
              ·{" "}
              <Link to="/admin/sources" className="font-semibold underline">
                {t("status.open_sources")}
              </Link>
            </>
          ) : null}
        </span>
      ))}
      <button
        type="button"
        className="hover:bg-black/10 rounded-sm ml-auto p-1"
        aria-label={t("status.dismiss")}
        onClick={() => {
          try {
            sessionStorage.setItem(KEY, signature);
          } catch {
            /* приватный режим */
          }
          setDismissed(signature);
        }}
      >
        <XIcon aria-hidden className="size-4" />
      </button>
    </div>
  );
}
