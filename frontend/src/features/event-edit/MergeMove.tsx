import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { ArticleInEvent, EventDetail } from "@/entities/event";
import { useMe } from "@/entities/user";
import { isAppError } from "@/shared/api";
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  Hint,
  toast,
} from "@/shared/ui";

import { EventPicker } from "./EventPicker";
import { useMerge, useMoveArticle } from "./useMergeMove";

const LOCKED = new Set(["READY", "PUBLISHED"]);

function useAllowed(e: EventDetail) {
  const me = useMe();
  return me.permissions.includes("events.merge") && !LOCKED.has(e.status);
}

/** «Mesclar com…» в шапке события (FE-T4.4). */
export function MergeButton({
  event,
  onOpenEvent,
}: {
  event: EventDetail;
  onOpenEvent?: (id: string) => void;
}) {
  const { t } = useTranslation(["event", "hints"]);
  const me = useMe();
  const merge = useMerge(event.id);
  const [open, setOpen] = useState(false);
  const [other, setOther] = useState<{ id: string; title: string; article_count: number } | null>(
    null,
  );
  if (!me.permissions.includes("events.merge")) return null;
  const locked = LOCKED.has(event.status);
  return (
    <>
      <Hint text={locked ? undefined : t("hints:event.merge")}>
        <Button
          size="sm"
          variant="outline"
          disabled={locked}
          title={locked ? t("merge.locked") : undefined}
          onClick={() => setOpen(true)}
        >
          {t("merge.button")}
        </Button>
      </Hint>
      <Dialog
        open={open}
        onOpenChange={(o) => {
          setOpen(o);
          if (!o) setOther(null);
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("merge.title")}</DialogTitle>
          </DialogHeader>
          {other ? (
            <p role="alert" className="text-sm">
              {t("merge.warning", { title: other.title, count: other.article_count })}
            </p>
          ) : (
            <EventPicker excludeId={event.id} onPick={setOther} />
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setOpen(false)}>
              {t("workflow.cancel")}
            </Button>
            <Button
              disabled={!other || merge.isPending}
              onClick={() =>
                other &&
                merge.mutate(
                  { otherId: other.id, version: event.version },
                  {
                    onSuccess: () => {
                      setOpen(false);
                      toast.success(t("merge.done"), {
                        action: onOpenEvent
                          ? { label: other.title, onClick: () => onOpenEvent(other.id) }
                          : undefined,
                      });
                      setOther(null);
                    },
                    onError: (err) => toast.error(isAppError(err) ? err.title : t("load_failed")),
                  },
                )
              }
            >
              {t("merge.confirm")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

/** Меню статьи: «Separar em novo evento», «Mover para outro evento…». */
export function MoveArticleMenu({
  event,
  article,
  onMoved,
}: {
  event: EventDetail;
  article: ArticleInEvent;
  onMoved?: (targetId: string, sourceEmpty: boolean) => void;
}) {
  const { t } = useTranslation("event");
  const allowed = useAllowed(event);
  const move = useMoveArticle(event.id);
  const [picking, setPicking] = useState(false);
  const me = useMe();
  if (!me.permissions.includes("events.merge")) return null;
  const run = (targetId: string | null) =>
    move.mutate(
      { articleId: article.id, targetId, version: event.version },
      {
        onSuccess: (r) => {
          setPicking(false);
          toast.success(t("move.done"));
          onMoved?.(r.target_event_id, r.source.article_count === 0);
        },
        onError: (err) => toast.error(isAppError(err) ? err.title : t("load_failed")),
      },
    );
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto h-6 px-2"
            aria-label={t("move.menu", { title: article.title })}
            disabled={!allowed}
          >
            ⋯
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuItem onSelect={() => run(null)}>{t("move.split")}</DropdownMenuItem>
          <DropdownMenuItem onSelect={() => setPicking(true)}>
            {t("move.to_other")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={picking} onOpenChange={setPicking}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t("move.to_other")}</DialogTitle>
          </DialogHeader>
          <EventPicker excludeId={event.id} onPick={(e) => run(e.id)} />
        </DialogContent>
      </Dialog>
    </>
  );
}
