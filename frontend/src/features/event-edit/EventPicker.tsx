import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { fetchEventsPage } from "@/entities/event";
import { Input } from "@/shared/ui";

/** Поиск события по тексту, текущее исключено (FE-T4.4 §11). */
export function EventPicker({
  excludeId,
  onPick,
}: {
  excludeId: string;
  onPick: (e: { id: string; title: string; article_count: number }) => void;
}) {
  const { t } = useTranslation("event");
  const [q, setQ] = useState("");
  const term = q.trim();
  const found = useQuery({
    queryKey: ["events", "picker", term],
    enabled: term.length >= 2,
    queryFn: () =>
      fetchEventsPage({ q: term, limit: 10, relevance: ["HIGH", "MEDIUM", "LOW", "IRRELEVANT"] }),
  });
  const items = (found.data?.items ?? []).filter((e) => e.id !== excludeId);
  return (
    <div className="space-y-2">
      <Input
        aria-label={t("merge.search")}
        placeholder={t("merge.search")}
        value={q}
        onChange={(e) => setQ(e.target.value)}
      />
      <ul
        role="listbox"
        aria-label={t("merge.results")}
        className="max-h-60 space-y-1 overflow-auto"
      >
        {items.map((e) => (
          <li key={e.id}>
            <button
              type="button"
              role="option"
              aria-selected={false}
              className="hover:bg-accent w-full rounded px-2 py-1 text-left text-sm"
              onClick={() => onPick(e)}
            >
              {e.title} <span className="text-muted-foreground text-xs">· {e.article_count}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
