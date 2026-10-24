import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getRouteApi, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { sourceKeys } from "@/entities/source";
import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import { formatDateTime } from "@/shared/lib/datetime";
import { Button, DataTable, HelpTip, Input, Label, Textarea, toast } from "@/shared/ui";

import { regionName } from "@/shared/lib/region";
import { adminSourceKeys, type SourceCreate, type SourceDetail, usePatchSource } from "./queries";

/** Поле формы → ключ подсказки в hints:source.* */
const FIELD_HINT: Partial<Record<string, string>> = {
  kind: "kind",
  tier: "tier",
  owner_group: "owner_group",
  parser_profile: "parser_profile",
  poll_interval_seconds: "poll",
  min_request_gap_ms: "gap",
  content_ttl_days: "ttl",
  region: "region",
};

type Kind = SourceCreate["kind"];
// ponytail: зеркало реестра профилей ingestion; неизвестное имя отклонит валидация сервера
const PROFILES: Record<Kind, string[]> = {
  rss: ["default"],
  sitemap: ["default"],
  html: ["telegram", "cbf"],
  calendar: ["holidays_openholidays", "holidays_brasilapi", "holidays_govuk", "holidays_ruwiki"],
  manual: ["default"],
};
/** Пример адреса ленты: по профилю, для RSS и sitemap — по типу */
const EXAMPLE: Record<string, string> = {
  rss: "https://ge.globo.com/rss/ge/",
  sitemap: "https://www.example.com/news-sitemap.xml",
  telegram: "https://t.me/s/channel_name",
  cbf: "https://www.cbf.com.br/futebol-brasileiro/noticias",
  holidays_openholidays:
    "https://openholidaysapi.org/PublicHolidays?countryIsoCode=FR&validFrom={year}-01-01&validTo={year}-12-31&languageIsoCode=EN",
  holidays_brasilapi: "https://brasilapi.com.br/api/feriados/v1/{year}",
  holidays_govuk: "https://www.gov.uk/bank-holidays.json",
  holidays_ruwiki: "https://ru.wikipedia.org/wiki/Праздники_России?year={year}",
};
const exampleFor = (f: { kind: Kind; parser_profile: string }) =>
  EXAMPLE[f.kind === "rss" || f.kind === "sitemap" ? f.kind : f.parser_profile];

const route = getRouteApi("/admin/sources/$sourceId");
const EMPTY: SourceCreate = {
  name: "",
  base_url: "https://",
  kind: "rss",
  feed_urls: [],
  tier: null,
  owner_group: null,
  language: "en",
  region: "BR",
  parser_profile: "default",
  poll_interval_seconds: 300,
  min_request_gap_ms: 2000,
  content_policy: "transient_text",
  content_ttl_days: 7,
  url_keep_params: [],
  tos_notes: "",
  active: true,
};
type Form = SourceCreate;
const FIELDS = Object.keys(EMPTY) as (keyof Form)[];

function toForm(d: SourceDetail): Form {
  return Object.fromEntries(FIELDS.map((k) => [k, d[k as keyof SourceDetail]])) as Form;
}

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

export function SourceFormPage() {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const me = useMe();
  const { sourceId } = route.useParams();
  const isNew = sourceId === "new";
  const navigate = useNavigate();
  const qc = useQueryClient();
  const detail = useQuery({
    queryKey: adminSourceKeys.detail(sourceId),
    enabled: !isNew,
    queryFn: () =>
      unwrap(api.GET("/api/v1/sources/{source_id}", { params: { path: { source_id: sourceId } } })),
  });
  const [form, setForm] = useState<Form>(EMPTY);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [existing, setExisting] = useState<string | null>(null);
  useEffect(() => {
    if (detail.data) setForm(toForm(detail.data));
  }, [detail.data]);
  const patch = usePatchSource(sourceId);
  const create = useMutation({
    mutationFn: (body: Form) => unwrap(api.POST("/api/v1/sources", { body })),
    onSuccess: (d) => {
      void qc.invalidateQueries({ queryKey: sourceKeys.all });
      void navigate({ to: "/admin/sources/$sourceId", params: { sourceId: d.id } });
    },
  });
  if (!me.permissions.includes("sources.manage")) return <p role="alert">{t("forbidden")}</p>;
  const onError = (e: unknown) => {
    if (isAppError(e) && e.code === "source.domain_exists")
      setExisting(
        String(
          (e as unknown as { extensions?: { source_id?: string } }).extensions?.source_id ?? "",
        ),
      );
    if (isAppError(e) && e.fieldErrors.length)
      setErrors(Object.fromEntries(e.fieldErrors.map((f) => [f.field, f.message])));
    else toast.error(isAppError(e) ? e.title : t("settings.failed"));
  };
  const submit = () => {
    setErrors({});
    if (isNew) create.mutate(form, { onError });
    else if (detail.data) {
      const base = toForm(detail.data);
      const changed = Object.fromEntries(
        FIELDS.filter((k) => k !== "kind" && !same(base[k], form[k])).map((k) => [k, form[k]]),
      );
      if (Object.keys(changed).length)
        patch.mutate(
          { patch: changed, version: detail.data.version },
          { onSuccess: () => toast.success(t("sources.saved")), onError },
        );
    }
  };
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  // новый тип — подходящий ему профиль; у «только вручную» лент нет
  const setKind = (kind: Kind) =>
    setForm((f) => ({
      ...f,
      kind,
      parser_profile: PROFILES[kind][0] ?? f.parser_profile,
      feed_urls: kind === "manual" ? [] : f.feed_urls,
    }));
  const profiles = PROFILES[form.kind].includes(form.parser_profile)
    ? PROFILES[form.kind]
    : [form.parser_profile, ...PROFILES[form.kind]];
  const example = exampleFor(form);
  const feedError = Object.entries(errors).find(([k]) => k.startsWith("feed_urls"))?.[1];
  const text = (k: keyof Form, label: string, hint?: string) => (
    <div className="space-y-1">
      <div className="flex items-center">
        <Label htmlFor={`s-${k}`}>{label}</Label>
        {FIELD_HINT[k] ? <HelpTip text={t(`hints:source.${FIELD_HINT[k]}`)} /> : null}
      </div>
      <Input
        id={`s-${k}`}
        value={String(form[k] ?? "")}
        aria-invalid={Boolean(errors[k])}
        aria-describedby={hint ? `s-${k}-hint` : undefined}
        onChange={(e) =>
          set(
            k,
            (e.target.value === "" && k === "owner_group"
              ? null
              : k === "region"
                ? e.target.value.toUpperCase().slice(0, 2)
                : e.target.value) as never,
          )
        }
      />
      {hint ? (
        <p id={`s-${k}-hint`} className="text-muted-foreground text-xs">
          {hint}
        </p>
      ) : null}
      {errors[k] ? <p className="text-destructive text-xs">{errors[k]}</p> : null}
    </div>
  );
  const num = (k: keyof Form, label: string) => (
    <div className="space-y-1">
      <div className="flex items-center">
        <Label htmlFor={`s-${k}`}>{label}</Label>
        {FIELD_HINT[k] ? <HelpTip text={t(`hints:source.${FIELD_HINT[k]}`)} /> : null}
      </div>
      <Input
        id={`s-${k}`}
        type="number"
        value={String(form[k])}
        onChange={(e) => set(k, Number(e.target.value) as never)}
      />
      {errors[k] ? <p className="text-destructive text-xs">{errors[k]}</p> : null}
    </div>
  );
  const select = (
    k: keyof Form,
    label: string,
    options: (string | null)[],
    disabled = false,
    optLabel: (o: string) => string = (o) => o,
    hint?: string,
  ) => (
    <div className="space-y-1">
      <div className="flex items-center">
        <Label htmlFor={`s-${k}`}>{label}</Label>
        {FIELD_HINT[k] ? <HelpTip text={t(`hints:source.${FIELD_HINT[k]}`)} /> : null}
      </div>
      <select
        id={`s-${k}`}
        disabled={disabled}
        className="border-input h-8 w-full rounded-md border bg-transparent px-2"
        value={String(form[k] ?? "")}
        onChange={(e) =>
          k === "kind" ? setKind(e.target.value as Kind) : set(k, (e.target.value || null) as never)
        }
      >
        {options.map((o) => (
          <option key={String(o)} value={o ?? ""}>
            {o === null ? "—" : optLabel(o)}
          </option>
        ))}
      </select>
      {hint ? <p className="text-muted-foreground text-xs">{hint}</p> : null}
      {errors[k] ? <p className="text-destructive text-xs">{errors[k]}</p> : null}
    </div>
  );
  return (
    <div className="space-y-6">
      <p>
        <Link to="/admin/sources" className="text-sm hover:underline">
          ← {t("section.sources")}
        </Link>
      </p>
      <form
        aria-label={t("sources.form")}
        className="grid gap-3 md:grid-cols-2"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        {text("name", t("sources.col.name"))}
        {text("base_url", t("sources.base_url"))}
        {select(
          "kind",
          t("sources.kind"),
          ["rss", "sitemap", "html", "calendar", "manual"],
          !isNew,
          (o) => t(`enums:SourceKind.${o}`),
        )}
        {select(
          "tier",
          t("sources.col.tier"),
          [null, "OFFICIAL", "A", "B", "C", "UNTRUSTED"],
          false,
          (o) => t(`enums:SourceTier.${o}`),
        )}
        <aside
          aria-label={t("sources.guide.title")}
          className="bg-muted/40 space-y-1 rounded-md border p-3 text-sm md:col-span-2"
        >
          <p className="font-medium">{t(`enums:SourceKind.${form.kind}`)}</p>
          <p className="text-muted-foreground whitespace-pre-line">
            {t(`sources.guide.${form.kind}`)}
          </p>
          {example ? (
            <p className="text-muted-foreground text-xs [overflow-wrap:anywhere]">
              {t("sources.guide.example")}: <code>{example}</code>
            </p>
          ) : null}
          {isNew ? (
            <p className="text-muted-foreground text-xs">{t("sources.guide.after")}</p>
          ) : null}
        </aside>
        {text("owner_group", t("sources.col.owner_group"), t("sources.owner_hint"))}
        {text("region", t("sources.region"), regionName(String(form.region ?? "")))}
        {select("parser_profile", t("sources.parser_profile"), profiles, false, (o) =>
          t(`sources.profiles.${o}`, { defaultValue: o }),
        )}
        {num("poll_interval_seconds", t("sources.poll"))}
        {num("min_request_gap_ms", t("sources.gap"))}
        {select(
          "content_policy",
          t("sources.policy"),
          ["transient_text", "snippet_only"],
          false,
          (o) => t(`enums:ContentPolicy.${o}`),
          t("sources.policy_hint"),
        )}
        {num("content_ttl_days", t("sources.ttl"))}
        {form.kind === "manual" ? null : (
          <div className="space-y-1 md:col-span-2">
            <Label htmlFor="s-feeds">{t(`sources.feeds_label.${form.kind}`)}</Label>
            <Textarea
              id="s-feeds"
              rows={3}
              placeholder={example}
              aria-invalid={Boolean(feedError)}
              value={form.feed_urls?.join("\n") ?? ""}
              onChange={(e) =>
                set(
                  "feed_urls",
                  e.target.value
                    .split("\n")
                    .map((x) => x.trim())
                    .filter(Boolean),
                )
              }
            />
            {feedError ? <p className="text-destructive text-xs">{feedError}</p> : null}
          </div>
        )}
        <div className="space-y-1 md:col-span-2">
          <Label htmlFor="s-tos">{t("sources.tos")}</Label>
          <Textarea
            id="s-tos"
            value={form.tos_notes ?? ""}
            onChange={(e) => set("tos_notes", e.target.value)}
          />
        </div>
        {existing !== null ? (
          <p role="alert" className="text-destructive text-sm md:col-span-2">
            {t("sources.exists")}{" "}
            {existing ? (
              <Link
                to="/admin/sources/$sourceId"
                params={{ sourceId: existing }}
                className="underline"
              >
                {t("sources.open_existing")}
              </Link>
            ) : null}
          </p>
        ) : null}
        <div className="md:col-span-2">
          <Button type="submit" disabled={create.isPending || patch.isPending}>
            {isNew ? t("sources.create") : t("sources.save")}
          </Button>
        </div>
      </form>
      {!isNew && detail.data ? (
        <>
          <SourceTestPanel sourceId={sourceId} disabled={detail.data.kind === "manual"} />
          <FetchRuns sourceId={sourceId} timeZone={me.timezone} />
        </>
      ) : null}
    </div>
  );
}

type TestResult = import("@/shared/api").components["schemas"]["SourceTestResult"];

function SourceTestPanel({ sourceId, disabled }: { sourceId: string; disabled: boolean }) {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const [testId, setTestId] = useState<string | null>(null);
  const start = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/sources/{source_id}:test", { params: { path: { source_id: sourceId } } }),
      ),
  });
  const result = useQuery({
    queryKey: ["source-test", testId],
    enabled: Boolean(testId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/sources/tests/{test_id}", { params: { path: { test_id: testId ?? "" } } }),
      ),
    refetchInterval: (q) => (q.state.data?.status === "pending" ? 1500 : false),
  });
  const r: TestResult | undefined = result.data;
  return (
    <section aria-labelledby="test-h" className="space-y-2">
      <h3 id="test-h" className="font-medium">
        {t("sources.test")}
        <HelpTip text={t("hints:source.test")} />
      </h3>
      <Button
        size="sm"
        variant="outline"
        disabled={disabled || start.isPending || r?.status === "pending"}
        onClick={() => start.mutate(undefined, { onSuccess: (d) => setTestId(d.test_id) })}
      >
        {t("sources.test_run")}
      </Button>
      {r?.status === "pending" ? <p aria-busy="true">{t("sources.testing")}</p> : null}
      {r && r.status !== "pending" ? (
        <div className="space-y-2 text-sm">
          {r.feeds.map((f) => {
            const feed = f as {
              feed_url: string;
              status: string;
              error_code: string | null;
              items: { url: string; title: string }[];
            };
            return (
              <div key={feed.feed_url}>
                <p className="font-medium">
                  {feed.feed_url} ·{" "}
                  {feed.status === "ok"
                    ? t("sources.items", { count: feed.items.length })
                    : feed.error_code}
                </p>
                <ul className="list-disc pl-5">
                  {feed.items.map((i) => (
                    <li key={i.url}>{i.title}</li>
                  ))}
                </ul>
              </div>
            );
          })}
          {r.sample ? (
            <dl className="grid grid-cols-[8rem_1fr] gap-x-2 rounded border p-2">
              {Object.entries(r.sample).map(([k, v]) => (
                <div key={k} className="contents">
                  <dt className="text-muted-foreground">{k}</dt>
                  <dd className="[overflow-wrap:anywhere]">{String(v ?? "—")}</dd>
                </div>
              ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function FetchRuns({ sourceId, timeZone }: { sourceId: string; timeZone: string }) {
  const { t } = useTranslation(["admin", "hints", "enums"]);
  const runs = useQuery({
    queryKey: adminSourceKeys.runs(sourceId),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/sources/{source_id}/runs", { params: { path: { source_id: sourceId } } }),
      ),
  });
  return (
    <section aria-labelledby="runs-h" className="space-y-2">
      <h3 id="runs-h" className="font-medium">
        {t("sources.runs")}
      </h3>
      <DataTable>
        <thead>
          <tr>
            <th>{t("sources.run_at")}</th>
            <th>{t("sources.run_status")}</th>
            <th>{t("sources.run_items")}</th>
            <th>{t("sources.run_error")}</th>
          </tr>
        </thead>
        <tbody>
          {(runs.data?.items ?? []).map((r) => (
            <tr key={r.id}>
              <td>{formatDateTime(r.started_at, timeZone)}</td>
              <td>{r.status}</td>
              <td>
                {r.items_new}/{r.items_seen}
              </td>
              <td>{r.error_code ?? ""}</td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </section>
  );
}
