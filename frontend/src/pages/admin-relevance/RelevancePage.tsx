import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { RelevanceBadge } from "@/entities/event";
import { api, isAppError, unwrap, type components } from "@/shared/api";
import type { Relevance } from "@/shared/routing";
import { cn } from "@/shared/lib/utils";
import { Button, HelpTip, Input, Label, Textarea, toast } from "@/shared/ui";

type Result = components["schemas"]["RelevanceResult"];
// Слова ищутся в текстах статей — поэтому они на языках источников, а не интерфейса
const SOURCE_LANGS = ["pt-BR", "en", "ru"] as const;
type SourceLang = (typeof SOURCE_LANGS)[number];
type Words = Partial<Record<SourceLang, string[]>>;
interface Rule {
  name: string;
  weight: number;
  words: Words;
}
/** Часть enrich_rules, от которой зависит балл важности; остальное (виды спорта и т. п.)
 * сохраняется как было. */
interface Rules {
  relevance_rules: Rule[];
  competition_weight: Record<string, number>;
  level_thresholds: { HIGH: number; MEDIUM: number; LOW: number };
  body_weight: number;
  top_team_bonus: number;
  rumor_penalty: number;
  clickbait_penalty: number;
  rumor_markers: Words;
  version: number;
  [k: string]: unknown;
}

const KEY = ["settings", "enrich_rules"] as const;
const words = (s: string) =>
  s
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean);

/** «Важность»: из чего складывается балл, правила с весами и проверка на любом заголовке —
 * по несохранённым правилам, чтобы видеть эффект до сохранения. */
export function RelevancePage() {
  const { t } = useTranslation(["admin", "hints"]);
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: KEY,
    queryFn: () =>
      unwrap(api.GET("/api/v1/settings/{key}", { params: { path: { key: "enrich_rules" } } })),
  });
  const [form, setForm] = useState<Rules | null>(null);
  useEffect(() => {
    if (q.data) setForm(q.data.value as Rules);
  }, [q.data]);
  const save = useMutation({
    // версия правил попадает в метку обогащения (rules/vN): видно, по каким правилам оценена статья
    mutationFn: (v: Rules) =>
      unwrap(
        api.PUT("/api/v1/settings/{key}", {
          params: { path: { key: "enrich_rules" } },
          body: { value: { ...v, version: v.version + 1 } },
        }),
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["settings"] });
      toast.success(t("relevance.saved"));
    },
    onError: (e) =>
      toast.error(
        isAppError(e)
          ? [e.title, ...e.fieldErrors.map((f) => `${f.field}: ${f.message}`)].join(" · ")
          : t("relevance.save_failed"),
      ),
  });

  if (!form) return <p aria-busy="true">{t("relevance.loading")}</p>;
  const set = <K extends keyof Rules>(k: K, v: Rules[K]) => setForm((f) => f && { ...f, [k]: v });
  const setRule = (i: number, r: Partial<Rule>) =>
    set(
      "relevance_rules",
      form.relevance_rules.map((x, j) => (j === i ? { ...x, ...r } : x)),
    );
  const th = form.level_thresholds;
  const invalid = th.HIGH <= th.MEDIUM || form.relevance_rules.some((r) => !r.name.trim());
  const dirty = JSON.stringify(form) !== JSON.stringify(q.data?.value);

  return (
    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_24rem]">
      <div className="space-y-6">
        <HowItWorks rules={form} />
        <section aria-labelledby="rel-levels" className="space-y-3">
          <h2 id="rel-levels" className="font-medium">
            {t("relevance.levels")}
          </h2>
          <div className="grid gap-3 sm:grid-cols-3">
            <Num
              id="rel-high"
              label={t("relevance.threshold_high")}
              hint={t("hints:relevance.threshold_high")}
              value={th.HIGH}
              onChange={(v) => set("level_thresholds", { ...th, HIGH: v })}
            />
            <Num
              id="rel-medium"
              label={t("relevance.threshold_medium")}
              hint={t("hints:relevance.threshold_medium")}
              value={th.MEDIUM}
              onChange={(v) => set("level_thresholds", { ...th, MEDIUM: v })}
            />
            <Num
              id="rel-body"
              label={t("relevance.body_weight")}
              hint={t("hints:relevance.body_weight")}
              value={form.body_weight}
              step={0.1}
              min={0}
              max={2}
              onChange={(v) => set("body_weight", v)}
            />
            <Num
              id="rel-team"
              label={t("relevance.top_team_bonus")}
              hint={t("hints:relevance.top_team_bonus")}
              value={form.top_team_bonus}
              min={0}
              max={10}
              onChange={(v) => set("top_team_bonus", v)}
            />
            <Num
              id="rel-rumor"
              label={t("relevance.rumor_penalty")}
              hint={t("hints:relevance.rumor_penalty")}
              value={form.rumor_penalty}
              min={0}
              max={10}
              onChange={(v) => set("rumor_penalty", v)}
            />
            <Num
              id="rel-clickbait"
              label={t("relevance.clickbait_penalty")}
              hint={t("hints:relevance.clickbait_penalty")}
              value={form.clickbait_penalty}
              min={0}
              max={10}
              onChange={(v) => set("clickbait_penalty", v)}
            />
          </div>
          {th.HIGH <= th.MEDIUM ? (
            <p role="alert" className="text-destructive text-sm">
              {t("relevance.thresholds_invalid")}
            </p>
          ) : null}
        </section>

        <section aria-labelledby="rel-rules" className="space-y-3">
          <h2 id="rel-rules" className="font-medium">
            {t("relevance.rules")}
            <HelpTip text={t("hints:relevance.rules")} />
          </h2>
          <ul className="space-y-2">
            {form.relevance_rules.map((r, i) => (
              <li
                key={i}
                aria-label={r.name || t("relevance.rule_new")}
                className="grid gap-2 rounded-md border p-2 sm:grid-cols-[minmax(0,1fr)_6rem_auto]"
              >
                <Input
                  aria-label={t("relevance.rule_name")}
                  value={r.name}
                  placeholder={t("relevance.rule_name")}
                  onChange={(e) => setRule(i, { name: e.target.value })}
                />
                <Input
                  type="number"
                  aria-label={t("relevance.rule_weight")}
                  title={t("relevance.rule_points", {
                    title: r.weight * 2,
                    body: Math.round(r.weight * form.body_weight),
                  })}
                  min={-5}
                  max={5}
                  value={r.weight}
                  onChange={(e) => setRule(i, { weight: Number(e.target.value) })}
                />
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("relevance.rule_delete", { name: r.name })}
                  onClick={() =>
                    set(
                      "relevance_rules",
                      form.relevance_rules.filter((_, j) => j !== i),
                    )
                  }
                >
                  ✕
                </Button>
                <WordsByLanguage
                  className="sm:col-span-3"
                  label={r.name}
                  value={r.words}
                  onChange={(words) => setRule(i, { words })}
                />
              </li>
            ))}
          </ul>
          <Button
            size="sm"
            variant="outline"
            onClick={() =>
              set("relevance_rules", [...form.relevance_rules, { name: "", weight: 1, words: {} }])
            }
          >
            {t("relevance.rule_add")}
          </Button>
        </section>

        <section aria-labelledby="rel-comps" className="space-y-3">
          <h2 id="rel-comps" className="font-medium">
            {t("relevance.competitions")}
            <HelpTip text={t("hints:relevance.competitions")} />
          </h2>
          <ul className="space-y-2">
            {Object.entries(form.competition_weight).map(([name, w], i) => (
              <li key={i} className="flex gap-2">
                <Input
                  aria-label={t("relevance.competition_name")}
                  value={name}
                  onChange={(e) =>
                    set(
                      "competition_weight",
                      Object.fromEntries(
                        Object.entries(form.competition_weight).map(([k, v], j) =>
                          j === i ? [e.target.value, v] : [k, v],
                        ),
                      ),
                    )
                  }
                />
                <Input
                  type="number"
                  className="w-24"
                  aria-label={t("relevance.competition_weight")}
                  value={w}
                  onChange={(e) =>
                    set("competition_weight", {
                      ...form.competition_weight,
                      [name]: Number(e.target.value),
                    })
                  }
                />
                <Button
                  size="sm"
                  variant="ghost"
                  aria-label={t("relevance.competition_delete", { name })}
                  onClick={() =>
                    set(
                      "competition_weight",
                      Object.fromEntries(
                        Object.entries(form.competition_weight).filter(([k]) => k !== name),
                      ),
                    )
                  }
                >
                  ✕
                </Button>
              </li>
            ))}
          </ul>
          <Button
            size="sm"
            variant="outline"
            disabled={"" in form.competition_weight}
            onClick={() => set("competition_weight", { ...form.competition_weight, "": 1 })}
          >
            {t("relevance.competition_add")}
          </Button>
        </section>

        <section aria-labelledby="rel-markers" className="space-y-2">
          <h2 id="rel-markers" className="font-medium">
            {t("relevance.rumor_markers")}
            <HelpTip text={t("hints:relevance.rumor_markers")} />
          </h2>
          <WordsByLanguage
            label={t("relevance.rumor_markers")}
            value={form.rumor_markers}
            onChange={(v) => set("rumor_markers", v)}
          />
        </section>

        <div className="bg-background sticky bottom-0 flex flex-wrap items-center gap-2 border-t py-3">
          <Button
            disabled={!dirty || invalid || save.isPending}
            onClick={() =>
              save.mutate({
                ...form,
                competition_weight: Object.fromEntries(
                  Object.entries(form.competition_weight).filter(([k]) => k.trim()),
                ),
              })
            }
          >
            {t("relevance.save")}
          </Button>
          <Button
            variant="ghost"
            disabled={!dirty}
            onClick={() => q.data && setForm(q.data.value as Rules)}
          >
            {t("relevance.reset")}
          </Button>
          <p className="text-muted-foreground text-xs">{t("relevance.applies")}</p>
        </div>
      </div>
      <Checker rules={form} />
    </div>
  );
}

/** Формула словами — с текущими числами из формы. */
function HowItWorks({ rules }: { rules: Rules }) {
  const { t } = useTranslation(["admin", "enums"]);
  const th = rules.level_thresholds;
  const steps = [
    t("relevance.how.not_sports"),
    t("relevance.how.rules", { body: rules.body_weight }),
    t("relevance.how.competition"),
    t("relevance.how.team", { n: rules.top_team_bonus }),
    t("relevance.how.penalties", {
      rumor: rules.rumor_penalty,
      clickbait: rules.clickbait_penalty,
    }),
    t("relevance.how.levels", { high: th.HIGH, medium: th.MEDIUM }),
    t("relevance.how.event"),
  ];
  return (
    <section aria-labelledby="rel-how" className="bg-muted/30 space-y-2 rounded-md border p-4">
      <h2 id="rel-how" className="font-medium">
        {t("relevance.how.title")}
      </h2>
      <ol className="list-decimal space-y-1 pl-5 text-sm">
        {steps.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ol>
      <Scale high={th.HIGH} medium={th.MEDIUM} />
    </section>
  );
}

/** Шкала баллов: где кончается низкая и начинается высокая. */
function Scale({ high, medium, score }: { high: number; medium: number; score?: number }) {
  const { t } = useTranslation("enums");
  const max = Math.max(high + 4, (score ?? 0) + 1);
  const at = (n: number) => `${(Math.max(0, Math.min(n, max)) / max) * 100}%`;
  return (
    <div className="space-y-1" aria-hidden="true">
      <div className="relative flex h-2 overflow-hidden rounded-full">
        <span className="bg-muted h-full" style={{ width: at(medium) }} />
        <span className="bg-input h-full" style={{ width: `calc(${at(high)} - ${at(medium)})` }} />
        <span className="bg-attention h-full flex-1" />
        {score !== undefined ? (
          <span className="bg-foreground absolute top-0 h-full w-0.5" style={{ left: at(score) }} />
        ) : null}
      </div>
      <div className="text-muted-foreground relative h-4 text-[11px]">
        <span className="absolute left-0">{t("Relevance.LOW")}</span>
        <span className="absolute -translate-x-1/2" style={{ left: at(medium) }}>
          {medium}
        </span>
        <span className="absolute -translate-x-1/2" style={{ left: at(high) }}>
          {high}
        </span>
        <span className="absolute right-0">{t("Relevance.HIGH")}</span>
      </div>
    </div>
  );
}

/** Проверка на заголовке: какой балл и уровень дадут правила из формы (ещё не сохранённые). */
function Checker({ rules }: { rules: Rules }) {
  const { t } = useTranslation(["admin", "hints"]);
  const [title, setTitle] = useState("");
  const [lead, setLead] = useState("");
  const check = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/relevance:check", {
          body: { title, lead, rules, url: "https://example.com/" },
        }),
      ),
  });
  const r: Result | undefined = check.data;
  // правила поменяли — проверенный заголовок пересчитывается сам
  const rulesKey = JSON.stringify(rules);
  useEffect(() => {
    if (!check.data || !title.trim()) return;
    const id = setTimeout(() => check.mutate(), 400);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- только при смене правил
  }, [rulesKey]);
  return (
    <aside aria-labelledby="rel-check" className="space-y-3 xl:sticky xl:top-4 xl:self-start">
      <form
        className="space-y-2 rounded-md border p-4"
        onSubmit={(e) => {
          e.preventDefault();
          check.mutate();
        }}
      >
        <h2 id="rel-check" className="font-medium">
          {t("relevance.check.title")}
          <HelpTip text={t("hints:relevance.check")} />
        </h2>
        <Label htmlFor="rel-check-title">{t("relevance.check.headline")}</Label>
        <Input id="rel-check-title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Label htmlFor="rel-check-lead">{t("relevance.check.lead")}</Label>
        <Textarea
          id="rel-check-lead"
          rows={3}
          value={lead}
          onChange={(e) => setLead(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={!title.trim() || check.isPending}>
          {t("relevance.check.run")}
        </Button>
        {check.isError ? (
          <p role="alert" className="text-destructive text-sm">
            {isAppError(check.error) ? check.error.title : t("relevance.check.failed")}
          </p>
        ) : null}
      </form>
      {r ? (
        <section
          aria-label={t("relevance.check.result")}
          className="space-y-2 rounded-md border p-4"
        >
          <div className="flex items-center gap-2">
            <RelevanceBadge level={r.level as Relevance} />
            {r.is_sports ? (
              <span className="text-sm tabular-nums">
                {t("relevance.check.score", { score: r.score })}
              </span>
            ) : null}
          </div>
          {r.is_sports ? (
            <>
              <Scale
                high={rules.level_thresholds.HIGH}
                medium={rules.level_thresholds.MEDIUM}
                score={r.score}
              />
              {r.parts.length ? (
                <ul aria-label={t("relevance.check.parts")} className="space-y-1 text-sm">
                  {r.parts.map((p, i) => (
                    <li key={i} className="flex justify-between gap-2">
                      <span className="min-w-0">
                        {p.kind === "rule"
                          ? t(`relevance.check.part_rule_${p.where}`, { name: p.name })
                          : t(`relevance.check.part_${p.kind}`, { name: p.name })}
                      </span>
                      <span className="shrink-0 font-medium tabular-nums">
                        {p.points > 0 ? `+${p.points}` : p.points}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-muted-foreground text-sm">{t("relevance.check.no_signals")}</p>
              )}
            </>
          ) : (
            <p className="text-muted-foreground text-sm">{t("relevance.check.not_sports")}</p>
          )}
        </section>
      ) : null}
    </aside>
  );
}

function Num({
  id,
  label,
  hint,
  value,
  onChange,
  step = 1,
  min,
  max,
}: {
  id: string;
  label: string;
  hint: string;
  value: number;
  onChange: (v: number) => void;
  step?: number;
  min?: number;
  max?: number;
}) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>
        {label}
        <HelpTip text={hint} />
      </Label>
      <Input
        id={id}
        type="number"
        step={step}
        min={min}
        max={max}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  );
}

/** Слова по языкам источников. Текст правится свободно, разбирается при уходе из поля:
 * иначе запятая пропадала бы сразу и следующее слово не дописать. */
function WordsByLanguage({
  label,
  value,
  onChange,
  className,
}: {
  label: string;
  value: Words;
  onChange: (v: Words) => void;
  className?: string;
}) {
  const { t } = useTranslation(["admin", "hints"]);
  return (
    <div className={cn("grid gap-2 md:grid-cols-3", className)}>
      {SOURCE_LANGS.map((l) => (
        <WordsField
          key={l}
          label={t(`relevance.words_in.${l}`)}
          aria={`${label}: ${t(`relevance.words_in.${l}`)}`}
          value={value[l] ?? []}
          onChange={(ws) =>
            onChange(
              Object.fromEntries(
                Object.entries({ ...value, [l]: ws }).filter(([, x]) => x.length),
              ) as Words,
            )
          }
        />
      ))}
    </div>
  );
}

function WordsField({
  label,
  aria,
  value,
  onChange,
}: {
  label: string;
  aria: string;
  value: string[];
  onChange: (v: string[]) => void;
}) {
  const joined = value.join(", ");
  const [text, setText] = useState(joined);
  useEffect(() => setText(joined), [joined]);
  return (
    <label className="space-y-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <Textarea
        aria-label={aria}
        rows={2}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => onChange(words(text))}
      />
    </label>
  );
}
