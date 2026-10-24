import { getRouteApi } from "@tanstack/react-router";
import { useMemo } from "react";
import { useTranslation } from "react-i18next";

import { useArticlesInfinite, type ArticleFilters } from "@/entities/article";
import { useSourcesBrief } from "@/entities/source";
import { useMe } from "@/entities/user";
import { MultiSelectFilter, PeriodFilter, SearchInput } from "@/features/filters";
import { AddUrlDialog } from "@/features/manual-ingest";
import { periodToRange } from "@/shared/lib/datetime";
import { ARTICLE_STATE } from "@/shared/routing";
import { Button, Skeleton } from "@/shared/ui";

import { ArticlesTable } from "./ArticlesTable";

const route = getRouteApi("/articles");

export function ArticlesPage() {
  const { t } = useTranslation(["articles", "enums", "common"]);
  const search = route.useSearch();
  const me = useMe();
  const sources = useSourcesBrief();

  const period = search.period ?? "24h";
  // Граница периода фиксируется при смене периода: ключ запроса стабилен между рендерами.
  const filters: ArticleFilters = useMemo(
    () => ({
      source: search.source ?? [],
      state: search.state ?? [],
      q: search.q,
      ...periodToRange(period, new Date(), { from: search.from, to: search.to }),
    }),
    [search.source, search.state, search.q, period, search.from, search.to],
  );
  const list = useArticlesInfinite(filters);
  const items = list.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <section
      className="mx-auto max-w-[120rem] space-y-4 p-6 xl:px-8"
      aria-labelledby="articles-title"
    >
      <div className="flex items-center justify-between">
        <h1 id="articles-title" className="font-display text-2xl font-bold">
          {t("common:nav.articles")}
        </h1>
        <AddUrlDialog />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <SearchInput />
        <MultiSelectFilter
          name="source"
          label={t("col.source")}
          options={(sources.data ?? []).map((s) => ({ value: s.id, label: s.name }))}
        />
        <MultiSelectFilter
          name="state"
          label={t("col.state")}
          options={ARTICLE_STATE.map((s) => ({ value: s, label: t(`enums:ArticleState.${s}`) }))}
        />
        <PeriodFilter />
      </div>

      {list.isPending ? (
        <div className="space-y-2" aria-busy="true">
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : list.isError ? (
        <div role="alert" className="space-y-2">
          <p>{t("load_failed")}</p>
          <Button variant="outline" onClick={() => void list.refetch()}>
            {t("common:retry")}
          </Button>
        </div>
      ) : items.length === 0 ? (
        <p className="text-muted-foreground">{t("empty")}</p>
      ) : (
        <ArticlesTable
          items={items}
          timeZone={me.timezone}
          hasMore={Boolean(list.hasNextPage)}
          onMore={() => {
            if (!list.isFetchingNextPage) void list.fetchNextPage();
          }}
        />
      )}
    </section>
  );
}
