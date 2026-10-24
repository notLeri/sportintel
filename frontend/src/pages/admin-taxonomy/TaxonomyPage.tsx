import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { taxonomyKeys, useSportName, useSports } from "@/entities/taxonomy";
import { useMe } from "@/entities/user";
import { api, isAppError, unwrap } from "@/shared/api";
import {
  Badge,
  Button,
  DataTable,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  HelpTip,
  Hint,
  Input,
  Label,
  StatusDot,
  type StatusTone,
  toast,
} from "@/shared/ui";

type Entity = import("@/shared/api").components["schemas"]["EntityAdminItem"];
type Unlinked = import("@/shared/api").components["schemas"]["UnlinkedItem"];
const KINDS = ["competition", "team", "player", "coach", "person", "venue"] as const;
const adminKeys = {
  entities: (f: object) => ["taxonomy-admin", "entities", f] as const,
  unlinked: ["taxonomy-admin", "unlinked"] as const,
};

const REVIEW_TONE: Record<string, StatusTone> = {
  approved: "success",
  pending: "warn",
  ignored: "neutral",
};

function useInvalidate() {
  const qc = useQueryClient();
  return () => {
    void qc.invalidateQueries({ queryKey: ["taxonomy-admin"] });
    void qc.invalidateQueries({ queryKey: taxonomyKeys.all });
  };
}

function errText(e: unknown) {
  return isAppError(e) ? [e.title, ...e.fieldErrors.map((f) => f.message)].join(" · ") : "";
}

function EntityForm({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation(["admin", "event"]);
  const sports = useSports();
  const invalidate = useInvalidate();
  const [v, setV] = useState({
    kind: "team",
    sport_id: "football",
    canonical_name: "",
    priority: 0,
    aliases: "",
  });
  const [error, setError] = useState<string | null>(null);
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/taxonomy/entities", {
          body: {
            kind: v.kind as Entity["kind"] as never,
            sport_id: v.sport_id || null,
            canonical_name: v.canonical_name.trim(),
            priority: v.priority,
            aliases: v.aliases
              .split(",")
              .map((x) => x.trim())
              .filter(Boolean),
          },
        }),
      ),
    onSuccess: () => {
      invalidate();
      onDone();
      toast.success(t("taxonomy.created"));
    },
    onError: (e) => setError(errText(e)),
  });
  const valid = v.canonical_name.trim().length >= 1 && v.canonical_name.length <= 120;
  return (
    <form
      aria-label={t("taxonomy.new_entity")}
      className="grid gap-2 md:grid-cols-2"
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) create.mutate();
      }}
    >
      <div className="space-y-1">
        <Label htmlFor="e-name">{t("taxonomy.name")}</Label>
        <Input
          id="e-name"
          maxLength={120}
          value={v.canonical_name}
          onChange={(e) => setV({ ...v, canonical_name: e.target.value })}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="e-kind">{t("taxonomy.kind")}</Label>
        <select
          id="e-kind"
          className="border-input h-8 w-full rounded-md border bg-transparent px-2"
          value={v.kind}
          onChange={(e) => setV({ ...v, kind: e.target.value })}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`taxonomy.kinds.${k}`)}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <Label htmlFor="e-sport">{t("taxonomy.sport")}</Label>
        <select
          id="e-sport"
          className="border-input h-8 w-full rounded-md border bg-transparent px-2"
          value={v.sport_id}
          onChange={(e) => setV({ ...v, sport_id: e.target.value })}
        >
          <option value="">—</option>
          {(sports.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.name}
            </option>
          ))}
        </select>
      </div>
      <div className="space-y-1">
        <div className="flex items-center">
          <Label htmlFor="e-prio">{t("taxonomy.priority")}</Label>
          <HelpTip text={t("hints:taxonomy.priority")} />
        </div>
        <Input
          id="e-prio"
          type="number"
          min={-1}
          max={2}
          value={v.priority}
          onChange={(e) => setV({ ...v, priority: Number(e.target.value) })}
        />
      </div>
      <div className="space-y-1 md:col-span-2">
        <Label htmlFor="e-aliases">{t("taxonomy.aliases_csv")}</Label>
        <Input
          id="e-aliases"
          value={v.aliases}
          onChange={(e) => setV({ ...v, aliases: e.target.value })}
        />
      </div>
      {error ? (
        <p role="alert" className="text-destructive text-sm md:col-span-2">
          {error}
        </p>
      ) : null}
      <div className="md:col-span-2">
        <Button type="submit" disabled={!valid || create.isPending}>
          {t("taxonomy.create")}
        </Button>
      </div>
    </form>
  );
}

function AliasesEditor({ e }: { e: Entity }) {
  const { t } = useTranslation(["admin", "hints"]);
  const invalidate = useInvalidate();
  const [alias, setAlias] = useState("");
  const add = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/taxonomy/entities/{entity_id}/aliases", {
          params: { path: { entity_id: e.id } },
          body: { alias: alias.trim() },
        }),
      ),
    onSuccess: () => {
      setAlias("");
      invalidate();
    },
  });
  const remove = useMutation({
    mutationFn: (a: string) =>
      unwrap(
        api.DELETE("/api/v1/taxonomy/entities/{entity_id}/aliases/{alias_norm}", {
          params: { path: { entity_id: e.id, alias_norm: norm(a) } },
        }),
      ),
    onSuccess: invalidate,
    onError: (err) => toast.error(errText(err)),
  });
  return (
    <div className="flex flex-wrap items-center gap-1">
      {e.aliases.map((a) => (
        <Badge key={a} variant="secondary" className="gap-1">
          {a}
          {norm(a) !== norm(e.canonical_name) ? (
            <button
              type="button"
              aria-label={t("taxonomy.remove_alias", { alias: a })}
              onClick={() => remove.mutate(a)}
            >
              ×
            </button>
          ) : null}
        </Badge>
      ))}
      <form
        className="flex gap-1"
        onSubmit={(ev) => {
          ev.preventDefault();
          if (alias.trim()) add.mutate();
        }}
      >
        <Input
          aria-label={t("taxonomy.add_alias_for", { name: e.canonical_name })}
          className="h-7 w-32"
          value={alias}
          onChange={(ev) => setAlias(ev.target.value)}
        />
        <Button type="submit" size="sm" variant="outline" className="h-7">
          +
        </Button>
      </form>
    </div>
  );
}

/** Нормализация как platform.text.normalize_name: без регистра и диакритики, пробелы схлопнуты. */
/** Название для показа на языках интерфейса; в текстах источников сущность ищется
 * по названию из источников и алиасам — они не меняются. */
function DisplayName({ e }: { e: Entity }) {
  const { t, i18n } = useTranslation(["admin", "hints"]);
  const invalidate = useInvalidate();
  const [open, setOpen] = useState(false);
  const names = e.name_i18n ?? {};
  const [v, setV] = useState({ ru: names.ru ?? "", en: names.en ?? "" });
  const shown = names[i18n.language] || e.canonical_name;
  const save = useMutation({
    mutationFn: () =>
      unwrap(
        api.PATCH("/api/v1/taxonomy/entities/{entity_id}", {
          params: { path: { entity_id: e.id } },
          body: { name_i18n: v },
          headers: { "If-Match": `"${e.version}"` },
        }),
      ),
    onSuccess: () => {
      invalidate();
      setOpen(false);
    },
    onError: (err) => toast.error(errText(err)),
  });
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-1">
        <span className="font-medium">{shown}</span>
        <Button
          size="sm"
          variant="ghost"
          className="h-6 px-1.5 text-xs"
          aria-expanded={open}
          onClick={() => setOpen((o) => !o)}
        >
          {t("taxonomy.display_name_edit")}
        </Button>
      </div>
      {shown !== e.canonical_name ? (
        <span className="text-muted-foreground block text-xs">
          {t("taxonomy.in_sources", { name: e.canonical_name })}
        </span>
      ) : null}
      {open ? (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={(ev) => {
            ev.preventDefault();
            save.mutate();
          }}
        >
          {(["ru", "en"] as const).map((l) => (
            <label key={l} className="space-y-0.5 text-xs">
              <span className="text-muted-foreground">{t(`taxonomy.display_name.${l}`)}</span>
              <Input
                className="h-7 w-48"
                value={v[l]}
                placeholder={e.canonical_name}
                onChange={(x) => setV({ ...v, [l]: x.target.value })}
              />
            </label>
          ))}
          <Button size="sm" className="h-7" type="submit" disabled={save.isPending}>
            {t("taxonomy.save")}
          </Button>
          <HelpTip text={t("hints:taxonomy.display_name")} />
        </form>
      ) : null}
    </div>
  );
}

function norm(s: string) {
  return s
    .normalize("NFKD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^\p{L}\p{N}]+/gu, " ")
    .trim();
}

function EntitiesTab() {
  const { t } = useTranslation(["admin", "hints"]);
  const sportName = useSportName();
  const invalidate = useInvalidate();
  const [f, setF] = useState<{ kind?: string; review_state?: string; q?: string }>({});
  const [creating, setCreating] = useState(false);
  const list = useQuery({
    queryKey: adminKeys.entities(f),
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/taxonomy/entities/admin", {
          params: { query: { kind: f.kind as never, review_state: f.review_state, q: f.q } },
        }),
      ),
  });
  const review = useMutation({
    mutationFn: ({ e, state }: { e: Entity; state: "approved" | "ignored" }) =>
      unwrap(
        api.PATCH("/api/v1/taxonomy/entities/{entity_id}", {
          params: { path: { entity_id: e.id } },
          body: { review_state: state },
          headers: { "If-Match": `"${e.version}"` },
        }),
      ),
    onSuccess: invalidate,
  });
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        <Input
          aria-label={t("taxonomy.search")}
          placeholder={t("taxonomy.search")}
          className="h-8 w-56"
          onChange={(e) => setF({ ...f, q: e.target.value || undefined })}
        />
        <select
          aria-label={t("taxonomy.kind")}
          className="border-input h-8 rounded-md border bg-transparent px-2"
          onChange={(e) => setF({ ...f, kind: e.target.value || undefined })}
        >
          <option value="">{t("taxonomy.all_kinds")}</option>
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {t(`taxonomy.kinds.${k}`)}
            </option>
          ))}
        </select>
        <select
          aria-label={t("taxonomy.review")}
          className="border-input h-8 rounded-md border bg-transparent px-2"
          onChange={(e) => setF({ ...f, review_state: e.target.value || undefined })}
        >
          <option value="">{t("taxonomy.all_states")}</option>
          {["approved", "pending", "ignored"].map((s) => (
            <option key={s} value={s}>
              {t(`taxonomy.review_states.${s}`)}
            </option>
          ))}
        </select>
        <Button size="sm" onClick={() => setCreating((c) => !c)}>
          {t("taxonomy.new_entity")}
        </Button>
      </div>
      {creating ? <EntityForm onDone={() => setCreating(false)} /> : null}
      <DataTable scroll wrapClassName="[--table-top:20.5rem]">
        <thead>
          <tr>
            <th>{t("taxonomy.name")}</th>
            <th>{t("taxonomy.kind")}</th>
            <th>{t("taxonomy.sport")}</th>
            <th className="shrink num">
              {t("taxonomy.priority")}
              <HelpTip text={t("hints:taxonomy.priority")} />
            </th>
            <th className="shrink">{t("taxonomy.review")}</th>
            <th>
              {t("taxonomy.aliases")}
              <HelpTip text={t("hints:taxonomy.aliases")} />
            </th>
          </tr>
        </thead>
        <tbody>
          {(list.data?.items ?? []).map((e) => (
            <tr key={e.id} className="align-top">
              <td>
                <DisplayName e={e} />
              </td>
              <td className="shrink">{t(`taxonomy.kinds.${e.kind}`)}</td>
              <td className="shrink">{e.sport_id ? sportName(e.sport_id) : "—"}</td>
              <td className="num">{e.priority}</td>
              <td className="shrink">
                <StatusDot tone={REVIEW_TONE[e.review_state] ?? "neutral"}>
                  {t(`taxonomy.review_states.${e.review_state}`)}
                </StatusDot>
                {e.review_state === "pending" ? (
                  <span className="ml-2 inline-flex gap-1">
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-6"
                      onClick={() => review.mutate({ e, state: "approved" })}
                    >
                      {t("taxonomy.approve")}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6"
                      onClick={() => review.mutate({ e, state: "ignored" })}
                    >
                      {t("taxonomy.ignore")}
                    </Button>
                  </span>
                ) : null}
              </td>
              <td>
                <AliasesEditor e={e} />
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
    </div>
  );
}

function SportsTab() {
  const { t } = useTranslation(["admin", "hints"]);
  const sports = useSports();
  const invalidate = useInvalidate();
  const [v, setV] = useState({ id: "", "pt-BR": "", en: "", ru: "", sort: 100 });
  const create = useMutation({
    mutationFn: () =>
      unwrap(
        api.POST("/api/v1/taxonomy/sports", {
          body: { id: v.id, name_i18n: { "pt-BR": v["pt-BR"], en: v.en, ru: v.ru }, sort: v.sort },
        }),
      ),
    onSuccess: () => {
      invalidate();
      setV({ id: "", "pt-BR": "", en: "", ru: "", sort: 100 });
    },
    onError: (e) => toast.error(errText(e)),
  });
  const toggle = useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      unwrap(
        api.PATCH("/api/v1/taxonomy/sports/{sport_id}", {
          params: { path: { sport_id: id } },
          body: { active },
        }),
      ),
    onSuccess: invalidate,
  });
  const valid = /^[a-z0-9_]{2,40}$/.test(v.id) && v["pt-BR"].trim() && v.en.trim() && v.ru.trim();
  return (
    <div className="space-y-3">
      <ul className="space-y-1 text-sm">
        {(sports.data ?? []).map((s) => (
          <li key={s.id} className="flex items-center gap-2">
            <span className="w-10 text-right">{s.sort}</span>
            <span className="font-medium">{s.id}</span>
            <span>{Object.values(s.name_i18n).join(" · ")}</span>
            <Button
              size="sm"
              variant="ghost"
              className="h-6"
              onClick={() => toggle.mutate({ id: s.id, active: false })}
            >
              {t("taxonomy.deactivate")}
            </Button>
          </li>
        ))}
      </ul>
      <form
        aria-label={t("taxonomy.new_sport")}
        className="flex flex-wrap items-end gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (valid) create.mutate();
        }}
      >
        {(["id", "pt-BR", "en", "ru"] as const).map((k) => (
          <div key={k} className="space-y-1">
            <Label htmlFor={`sp-${k}`}>{k}</Label>
            <Input
              id={`sp-${k}`}
              className="h-8 w-32"
              value={v[k]}
              onChange={(e) => setV({ ...v, [k]: e.target.value })}
            />
          </div>
        ))}
        <Button type="submit" size="sm" disabled={!valid}>
          {t("taxonomy.add_sport")}
        </Button>
      </form>
    </div>
  );
}

function ResolveUnlinkedDialog({ item, onClose }: { item: Unlinked; onClose: () => void }) {
  const { t } = useTranslation(["admin", "hints"]);
  const invalidate = useInvalidate();
  const [target, setTarget] = useState<{ id: string; name: string } | null>(null);
  const [q, setQ] = useState("");
  const found = useQuery({
    queryKey: ["taxonomy-admin", "pick", item.kind, q],
    enabled: q.trim().length >= 2,
    queryFn: () =>
      unwrap(
        api.GET("/api/v1/taxonomy/entities/admin", {
          params: { query: { kind: item.kind as never, q } },
        }),
      ),
  });
  const resolve = useMutation({
    mutationFn: (action: "link" | "create" | "ignore") =>
      unwrap(
        api.POST("/api/v1/taxonomy/unlinked/{mention_norm}:resolve", {
          params: { path: { mention_norm: item.mention_norm } },
          body: {
            kind: item.kind,
            sport_key: item.sport_key,
            action,
            entity_id: action === "link" ? (target?.id ?? null) : null,
            priority: 0,
          },
        }),
      ),
    onSuccess: () => {
      invalidate();
      onClose();
    },
    onError: (e) => toast.error(errText(e)),
  });
  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("taxonomy.resolve_title", { mention: item.mention })}</DialogTitle>
        </DialogHeader>
        <div className="space-y-2">
          <Input
            aria-label={t("taxonomy.link_to")}
            placeholder={t("taxonomy.link_to")}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <ul className="max-h-40 overflow-auto text-sm">
            {(found.data?.items ?? []).map((e) => (
              <li key={e.id}>
                <button
                  type="button"
                  aria-pressed={target?.id === e.id}
                  className="hover:underline"
                  onClick={() => setTarget({ id: e.id, name: e.canonical_name })}
                >
                  {e.canonical_name}
                </button>
              </li>
            ))}
          </ul>
        </div>
        <DialogFooter className="flex-wrap gap-2">
          <Button disabled={!target || resolve.isPending} onClick={() => resolve.mutate("link")}>
            {t("taxonomy.link")}
            {target ? `: ${target.name}` : ""}
          </Button>
          <Button
            variant="outline"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate("create")}
          >
            {t("taxonomy.create_entity")}
          </Button>
          <Button
            variant="ghost"
            disabled={resolve.isPending}
            onClick={() => resolve.mutate("ignore")}
          >
            {t("taxonomy.ignore")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function UnlinkedTab() {
  const { t } = useTranslation(["admin", "hints"]);
  const list = useQuery({
    queryKey: adminKeys.unlinked,
    queryFn: () => unwrap(api.GET("/api/v1/taxonomy/unlinked")),
  });
  const [open, setOpen] = useState<Unlinked | null>(null);
  return (
    <>
      <DataTable>
        <thead>
          <tr>
            <th>{t("taxonomy.mention")}</th>
            <th>{t("taxonomy.kind")}</th>
            <th>{t("taxonomy.sport")}</th>
            <th className="shrink num">{t("taxonomy.occurrences")}</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(list.data?.items ?? []).map((u) => (
            <tr key={`${u.mention_norm}-${u.kind}-${u.sport_key}`}>
              <td className="font-medium">{u.mention}</td>
              <td>{t(`taxonomy.kinds.${u.kind}`, { defaultValue: u.kind })}</td>
              <td>{u.sport_id ?? "—"}</td>
              <td className="num">{u.occurrences}</td>
              <td className="shrink">
                <Button size="sm" variant="outline" onClick={() => setOpen(u)}>
                  {t("taxonomy.resolve")}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </DataTable>
      {open ? <ResolveUnlinkedDialog item={open} onClose={() => setOpen(null)} /> : null}
    </>
  );
}

export function TaxonomyPage() {
  const { t } = useTranslation(["admin", "hints"]);
  const me = useMe();
  const [tab, setTab] = useState<"entities" | "sports" | "unlinked">("entities");
  if (!me.permissions.includes("taxonomy.manage")) return <p role="alert">{t("forbidden")}</p>;
  return (
    <section aria-labelledby="tax-h" className="space-y-3">
      <h2 id="tax-h" className="text-lg font-semibold">
        {t("section.taxonomy")}
      </h2>
      <div role="tablist" className="flex gap-1">
        {(["entities", "sports", "unlinked"] as const).map((k) => (
          <Hint key={k} text={k === "sports" ? undefined : t(`hints:taxonomy.${k}`)}>
            <Button
              role="tab"
              size="sm"
              aria-selected={tab === k}
              variant={tab === k ? "default" : "outline"}
              onClick={() => setTab(k)}
            >
              {t(`taxonomy.tab.${k}`)}
            </Button>
          </Hint>
        ))}
      </div>
      {tab === "entities" ? <EntitiesTab /> : tab === "sports" ? <SportsTab /> : <UnlinkedTab />}
    </section>
  );
}
