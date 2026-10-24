import { Link } from "@tanstack/react-router";
import { ArrowUpRightIcon } from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { ArticleStateBadge, type ArticleListItem } from "@/entities/article";
import { SourceLabel } from "@/entities/source";
import { formatDateTime } from "@/shared/lib/datetime";
import { Badge, Button, DataTable } from "@/shared/ui";

interface Props {
  items: ArticleListItem[];
  timeZone: string;
  hasMore: boolean;
  onMore: () => void;
}

export function ArticlesTable({ items, timeZone, hasMore, onMore }: Props) {
  const { t } = useTranslation(["articles", "common"]);
  const sentinel = useRef<HTMLTableRowElement>(null);

  useEffect(() => {
    const el = sentinel.current;
    if (!el || !hasMore || typeof IntersectionObserver === "undefined") return;
    const io = new IntersectionObserver(
      (entries) => entries.some((e) => e.isIntersecting) && onMore(),
      {
        rootMargin: "400px",
      },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [hasMore, onMore]);

  return (
    <DataTable scroll wrapClassName="[--table-top:11.5rem]" aria-label={t("common:nav.articles")}>
      <thead>
        <tr>
          <th scope="col">{t("col.title")}</th>
          <th scope="col" className="shrink">
            {t("col.source")}
          </th>
          <th scope="col" className="shrink">
            {t("col.published")}
          </th>
          <th scope="col" className="shrink">
            {t("col.state")}
          </th>
          <th scope="col" className="shrink">
            {t("col.event")}
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((a) => (
          <tr key={a.id}>
            <td className="min-w-[22rem]">
              <a
                href={a.url}
                target="_blank"
                rel="noopener noreferrer"
                title={a.title_translated ? a.title : undefined}
                className="line-clamp-2 font-medium hover:underline"
              >
                {a.title_translated ?? a.title}
              </a>
              {a.manual ? (
                <Badge variant="outline" className="mt-1">
                  {t("manual")}
                </Badge>
              ) : null}
            </td>
            <td className="shrink">
              {a.source ? <SourceLabel name={a.source.name} tier={a.source.tier} /> : "—"}
            </td>
            <td className="shrink text-muted-foreground">
              {formatDateTime(a.published_at ?? a.discovered_at, timeZone)}
            </td>
            <td className="shrink">
              <ArticleStateBadge state={a.state} failureCode={a.failure_code} />
            </td>
            <td className="shrink">
              {a.event_id ? (
                <Link
                  to="/events/$eventId"
                  params={{ eventId: a.event_id }}
                  className="text-brand-text inline-flex items-center gap-1 font-medium hover:underline"
                >
                  {t("open_event")}
                  <ArrowUpRightIcon aria-hidden className="size-3.5" />
                </Link>
              ) : (
                <span className="text-muted-foreground">—</span>
              )}
            </td>
          </tr>
        ))}
        {hasMore ? (
          <tr ref={sentinel}>
            <td colSpan={5} className="text-center">
              <Button variant="ghost" size="sm" onClick={onMore}>
                {t("load_more")}
              </Button>
            </td>
          </tr>
        ) : null}
      </tbody>
    </DataTable>
  );
}
