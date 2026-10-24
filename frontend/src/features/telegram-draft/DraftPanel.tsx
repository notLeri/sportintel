import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { AiEventStatus, AiWait } from "@/entities/ai";
import { type DraftDetail, draftKeys, draftQuery, TelegramPreview } from "@/entities/draft";
import type { EventDetail } from "@/entities/event";
import { useMe, useSystemStatus } from "@/entities/user";
import { isAppError } from "@/shared/api";
import { bufferKey, clearBuffers, loadBuffer, saveBuffer } from "@/shared/lib/draft-autosave";
import { formatDateTime } from "@/shared/lib/datetime";
import { plainLength } from "@/shared/lib/telegram";
import { useOnline } from "@/shared/lib/useOnline";
import {
  Badge,
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  HelpTip,
  Hint,
  Label,
  toast,
} from "@/shared/ui";

import { CopyButton } from "./CopyButton";
import { DisclaimerBlock } from "./DisclaimerBlock";
import { DraftEditor } from "./DraftEditor";
import { LengthCounter } from "./LengthCounter";
import { PostFormat } from "./PostFormat";
import {
  type PostLang,
  useApprovePost,
  useGenerateDraft,
  useSaveDraft,
  useTranslateDraft,
} from "./useDraftMutations";
import { VersionHistory } from "./VersionHistory";

const DRAFTABLE = new Set(["SELECTED", "DRAFT", "READY"]);
const POST_LANGS: PostLang[] = ["ru", "en"];
const AUTOSAVE_MS = 1000;
const APPROVABLE = new Set(["NEW", "REVIEWING", "SELECTED", "DRAFT"]);

/** Блок черновика в деталях события (FE-T3.12). */
export function DraftPanel({
  event,
  timeZone,
  onCitationClick,
}: {
  event: EventDetail;
  timeZone: string;
  onCitationClick?: (n: number) => void;
}) {
  const { t } = useTranslation(["event", "hints"]);
  const gen = useGenerateDraft(event.id);
  // ИИ пишет короткий пост, если модель подключена; иначе — шаблон.
  const mode = useSystemStatus()?.ai.llm.available ? "llm" : "template";
  const draftId = event.draft?.id ?? gen.data?.id;
  const q = useQuery({ ...draftQuery(draftId ?? ""), enabled: Boolean(draftId) });
  const canDraft = DRAFTABLE.has(event.status) || Boolean(draftId);

  if (!draftId) {
    return (
      <section aria-label={t("draft_panel.title")} className="space-y-2 border-t pt-4">
        <h3 className="font-medium">
          {t("draft_panel.title")}
          <HelpTip text={t("hints:event.draft")} />
        </h3>
        <div className="flex flex-wrap gap-2">
          <Hint text={t(mode === "llm" ? "hints:draft.ai" : "hints:draft.template")}>
            <Button
              size="sm"
              aria-keyshortcuts="g"
              disabled={!canDraft || gen.isPending}
              onClick={() => gen.mutate({ mode })}
            >
              {gen.isPending
                ? t("draft_panel.generating")
                : t(mode === "llm" ? "draft_panel.ai" : "draft_panel.template")}
            </Button>
          </Hint>
          <Hint text={t("hints:draft.write")}>
            <Button
              size="sm"
              variant="outline"
              disabled={!canDraft || gen.isPending}
              onClick={() => gen.mutate({ mode: "empty" })}
            >
              {t("draft_panel.write")}
            </Button>
          </Hint>
        </div>
        <AiWait kind="rewrite" active={gen.isPending && mode === "llm"} />
        {!canDraft ? (
          <p className="text-muted-foreground text-xs">{t("draft_panel.select_first")}</p>
        ) : null}
        <PostFormat />
      </section>
    );
  }
  if (!q.data) return <p aria-busy="true">{t("draft_panel.loading")}</p>;
  return (
    <Ready
      key={`${q.data.id}`}
      draft={q.data}
      event={event}
      timeZone={timeZone}
      onCitationClick={onCitationClick}
      regenerate={() => gen.mutate({ mode, draftId })}
      regenerating={gen.isPending}
      aiRegenerating={gen.isPending && mode === "llm"}
    />
  );
}

function Ready({
  draft,
  event,
  timeZone,
  onCitationClick,
  regenerate,
  regenerating,
  aiRegenerating,
}: {
  draft: DraftDetail;
  event: EventDetail;
  timeZone: string;
  onCitationClick?: (n: number) => void;
  regenerate: () => void;
  regenerating: boolean;
  aiRegenerating: boolean;
}) {
  const { t } = useTranslation(["event", "hints"]);
  const online = useOnline();
  const save = useSaveDraft(draft.id, event.id);
  const tr = useTranslateDraft(draft.id, event.id);
  const approve = useApprovePost();
  const me = useMe();
  const canApprove =
    (me.allowed_transitions.DRAFT ?? []).some((o) => o.to === "READY") &&
    APPROVABLE.has(event.status);
  // ни один канал этот вариант не возьмёт — одобрять бессмысленно, причины показаны ниже
  const allBlocked = draft.channels.length > 0 && draft.channels.every((c) => c.blocked);
  const aiReady = useSystemStatus()?.ai.llm.available ?? false;
  const qc = useQueryClient();
  const cur = draft.current;
  const [body, setBody] = useState(cur?.body_tg_html ?? "");
  const [image, setImage] = useState(cur?.image_url ?? "");
  const [base, setBase] = useState({ n: cur?.n ?? 0, version: draft.version });
  const [touched, setTouched] = useState(false);
  const [history, setHistory] = useState(false);
  const [conflict, setConflict] = useState(false);
  const [restore, setRestore] = useState(() => {
    const b = loadBuffer(draft.id);
    return b && (!cur || b.value.savedAt > cur.created_at) ? b.value : null;
  });
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);

  // Новая версия с сервера (генерация, сохранение) — принять, если пользователь ничего не правит.
  useEffect(() => {
    if (!touched && cur && cur.n !== base.n) {
      setBody(cur.body_tg_html);
      setImage(cur.image_url ?? "");
      setBase({ n: cur.n, version: draft.version });
    }
  }, [cur, draft.version, base.n, touched]);

  useEffect(() => {
    if (!touched) return;
    clearTimeout(timer.current);
    timer.current = setTimeout(
      () =>
        saveBuffer(bufferKey(draft.id, base.n), {
          tgHtml: body,
          imageUrl: image || null,
          savedAt: new Date().toISOString(),
        }),
      AUTOSAVE_MS,
    );
    return () => clearTimeout(timer.current);
  }, [body, image, touched, draft.id, base.n]);

  useEffect(() => {
    if (!touched) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [touched]);

  const max = image ? 1024 : 4096;
  const length = plainLength(body);
  const imageValid = !image || /^https:\/\/\S+$/.test(image);
  const canSave =
    online &&
    touched &&
    length <= max &&
    imageValid &&
    draft.state !== "generating" &&
    !save.isPending;

  const doSave = (version = draft.version) => {
    if (!canSave) return;
    const wasReady = event.status === "READY";
    save.mutate(
      { version, body_tg_html: body, image_url: image || null },
      {
        onSuccess: (d) => {
          clearBuffers(draft.id);
          setTouched(false);
          setBase({ n: d.current?.n ?? base.n, version: d.version });
          toast.success(wasReady ? t("draft_panel.back_to_draft") : t("draft_panel.saved"));
        },
        onError: (err) => {
          if (isAppError(err) && err.status === 412) {
            void qc.invalidateQueries({ queryKey: draftKeys.detail(draft.id) });
            setConflict(true);
          } else toast.error(isAppError(err) ? err.title : t("draft_panel.save_failed"));
        },
      },
    );
  };
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
        e.preventDefault();
        doSave();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const edit = (v: string) => {
    setBody(v);
    setTouched(true);
  };
  const unverified =
    cur?.origin === "ai" && !touched
      ? (
          (
            cur.grounding as {
              sentences?: { text: string; status: string; unsupported_tokens?: string[] }[];
            } | null
          )?.sentences ?? []
        )
          .filter((s) => s.status !== "ok")
          .map((s) => ({
            text: s.text,
            title: `${t("draft_panel.unverified")}: ${(s.unsupported_tokens ?? []).join(", ")}`,
          }))
      : [];

  return (
    <section aria-label={t("draft_panel.title")} className="space-y-3 border-t pt-4">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="font-medium">
          {t("draft_panel.title")}
          <HelpTip text={t("hints:event.draft")} />
        </h3>
        {cur?.origin === "template" ? (
          <Badge variant="secondary">{t("draft.template_badge")}</Badge>
        ) : null}
        {cur ? <span className="text-muted-foreground text-xs">v{cur.n}</span> : null}
        {cur ? (
          <Hint text={t("hints:draft.lang")}>
            <Badge variant="outline">
              {t(`brief.lang.${cur.lang}`, { defaultValue: cur.lang })}
            </Badge>
          </Hint>
        ) : null}
        <span
          role="group"
          aria-label={t("draft_panel.translate_to")}
          className="ml-auto flex items-center gap-1"
        >
          <span className="text-muted-foreground text-xs">
            {tr.isPending ? t("draft_panel.translating") : t("draft_panel.translate_to")}
          </span>
          {POST_LANGS.map((l) => {
            const current = cur?.lang === l;
            const why = !aiReady
              ? t("draft_panel.ai_off")
              : touched
                ? t("draft_panel.save_before_translate")
                : current
                  ? t("draft_panel.already_in")
                  : t("hints:draft.translate");
            return (
              <Hint key={l} text={why}>
                {/* span: у disabled-кнопки нет hover, а подсказка объясняет, почему она недоступна */}
                <span>
                  <Button
                    size="sm"
                    variant={current ? "secondary" : "outline"}
                    aria-pressed={current}
                    disabled={current || !aiReady || touched || tr.isPending || regenerating}
                    onClick={() =>
                      tr.mutate(l, {
                        onError: () => toast.error(t("draft_panel.translate_failed")),
                      })
                    }
                  >
                    {t(`brief.lang.${l}`)}
                  </Button>
                </span>
              </Hint>
            );
          })}
        </span>
      </div>
      <ChannelTargets channels={draft.channels ?? []} lang={cur?.lang} />
      <AiWait kind="rewrite" active={aiRegenerating} />
      <AiWait kind="translate_post" active={tr.isPending} />
      {aiRegenerating ? null : <AiEventStatus eventId={event.id} kinds={["post", "rewrite"]} />}
      {!online ? (
        <p role="status" className="bg-warn-bg text-warn p-2 text-sm">
          {t("draft_panel.offline")}
        </p>
      ) : null}
      {restore ? (
        <div role="alert" className="flex flex-wrap items-center gap-2 bg-muted p-2 text-sm">
          {t("draft_panel.restore_banner", { time: formatDateTime(restore.savedAt, timeZone) })}
          <Button
            size="sm"
            onClick={() => {
              setBody(restore.tgHtml);
              setImage(restore.imageUrl ?? "");
              setTouched(true);
              setRestore(null);
            }}
          >
            {t("draft_panel.restore")}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              clearBuffers(draft.id);
              setRestore(null);
            }}
          >
            {t("draft_panel.discard")}
          </Button>
        </div>
      ) : null}
      {draft.state === "generating" ? <p aria-busy="true">{t("draft_panel.generating")}</p> : null}
      {draft.state === "failed" ? (
        <div role="alert" className="space-y-1 text-sm">
          <p>
            {t(`draft_panel.failure.${draft.failure_code ?? "generation_failed"}`, {
              defaultValue: t("draft_panel.failure.generation_failed"),
            })}
          </p>
          <Button size="sm" onClick={regenerate}>
            {t("draft_panel.retry")}
          </Button>
        </div>
      ) : null}
      <div className="grid gap-3 2xl:grid-cols-2">
        <div className="space-y-2">
          <DisclaimerBlock text={cur?.disclaimer_text ?? null} />
          <DraftEditor
            value={body}
            onChange={edit}
            onCitationClick={onCitationClick}
            unverified={unverified}
            readOnly={draft.state === "generating"}
          />
          <div className="flex items-center gap-2">
            <Label htmlFor="draft-image" className="shrink-0">
              {t("draft_panel.image")}
            </Label>
            <HelpTip text={t("hints:draft.image")} />
            <Input
              id="draft-image"
              type="url"
              placeholder="https://"
              value={image}
              aria-invalid={!imageValid}
              onChange={(e) => {
                setImage(e.target.value);
                setTouched(true);
              }}
            />
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <LengthCounter length={length} max={max} />
            {canApprove ? (
              <Hint
                text={
                  touched
                    ? t("draft_panel.save_before_approve")
                    : allBlocked
                      ? t("draft_panel.approve_blocked")
                      : t("hints:draft.approve")
                }
              >
                <span>
                  <Button
                    size="sm"
                    disabled={
                      touched || allBlocked || !cur?.body_tg_html.trim() || approve.isPending
                    }
                    onClick={() =>
                      approve.mutate(
                        { eventId: event.id, version: event.version },
                        {
                          onSuccess: () => toast.success(t("draft_panel.approved")),
                          onError: () => toast.error(t("draft_panel.approve_failed")),
                        },
                      )
                    }
                  >
                    {t("draft_panel.approve")}
                  </Button>
                </span>
              </Hint>
            ) : null}
            <Button
              size="sm"
              disabled={!canSave}
              aria-keyshortcuts="Control+S"
              onClick={() => doSave()}
            >
              {t("draft_panel.save")}
            </Button>
            <Hint text={t("hints:draft.regenerate")}>
              <Button
                size="sm"
                variant="outline"
                disabled={regenerating || draft.state === "generating"}
                onClick={regenerate}
              >
                {t("draft_panel.regenerate")}
              </Button>
            </Hint>
            <CopyButton
              disabled={touched || !cur}
              source={
                cur
                  ? {
                      draftId: draft.id,
                      versionN: cur.n,
                      tgHtml: cur.body_tg_html,
                    }
                  : null
              }
            />
            <Hint text={t("hints:draft.history")}>
              <Button
                size="sm"
                variant="ghost"
                aria-expanded={history}
                onClick={() => setHistory((h) => !h)}
              >
                {t("draft_panel.history")}
              </Button>
            </Hint>
          </div>
          {touched ? (
            <p className="text-muted-foreground text-xs">{t("draft_panel.save_before_copy")}</p>
          ) : null}
        </div>
        <TelegramPreview
          tgHtml={body}
          imageUrl={image || null}
          channelName={t("draft_panel.preview")}
        />
      </div>
      {history ? (
        <VersionHistory
          draft={draft}
          timeZone={timeZone}
          onRestore={(html) => {
            setBody(html);
            setTouched(true);
          }}
        />
      ) : null}
      <Dialog open={conflict} onOpenChange={setConflict}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("draft_panel.conflict_title")}</DialogTitle>
          </DialogHeader>
          <div className="grid gap-2 md:grid-cols-2">
            <div>
              <p className="text-xs font-medium">{t("draft_panel.server_version")}</p>
              <TelegramPreview tgHtml={cur?.body_tg_html ?? ""} imageUrl={null} channelName="" />
            </div>
            <div>
              <p className="text-xs font-medium">{t("draft_panel.your_version")}</p>
              <TelegramPreview tgHtml={body} imageUrl={null} channelName="" />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setTouched(false);
                setBase({ n: -1, version: draft.version });
                setConflict(false);
              }}
            >
              {t("draft_panel.use_server")}
            </Button>
            <Button
              onClick={() => {
                setConflict(false);
                doSave(draft.version);
              }}
            >
              {t("draft_panel.overwrite")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
      <PostFormat current={body} />
    </section>
  );
}

/** Куда уйдёт пост после «Готово» и почему может не уйти: язык, фильтры канала, давность. */
function ChannelTargets({
  channels,
  lang,
}: {
  channels: NonNullable<DraftDetail["channels"]>;
  lang: string | undefined;
}) {
  const { t } = useTranslation(["event", "hints"]);
  if (!lang || channels.length === 0) return null;
  const lname = (l: string) => t(`brief.lang.${l}`, { defaultValue: l });
  const right = channels.filter((c) => !c.blocked);
  const wrong = channels.filter((c) => c.blocked);
  return (
    <div className="space-y-1 text-sm">
      {wrong.map((c) => (
        <p key={c.name} role="status" className="bg-warn-bg text-warn p-2">
          {t(`draft_panel.channel_blocked.${c.blocked}`, {
            channel: `«${c.name}»`,
            channel_lang: lname(c.language),
            post_lang: lname(lang),
          })}
        </p>
      ))}
      {right.length ? (
        <p className="text-muted-foreground">
          {t("draft_panel.channel_target", {
            channels: right.map((c) => `«${c.name}»`).join(", "),
          })}
          {right.some((c) => !c.active) ? ` ${t("draft_panel.channel_off")}` : ""}
          <HelpTip text={t("hints:draft.channel_target")} />
        </p>
      ) : null}
    </div>
  );
}
