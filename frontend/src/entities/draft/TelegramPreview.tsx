import { EyeIcon } from "lucide-react";
import { type KeyboardEvent, type MouseEvent, type ReactNode, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { toDisplayHtml } from "@/shared/lib/telegram";
import { cn } from "@/shared/lib/utils";

/** Фон чата Telegram: обои по умолчанию (светлая и тёмная темы), см. .tg-wallpaper в styles.css. */
export const TG_CHAT_BG = "tg-wallpaper";

/** Пост в стиле канала Telegram (FE-T3.10). HTML санитизирован в toDisplayHtml (DOMPurify). */
export function TelegramPreview({
  tgHtml,
  imageUrl,
  channelName,
  withCitations = false,
}: {
  tgHtml: string;
  imageUrl: string | null;
  channelName: string;
  withCitations?: boolean;
}) {
  return (
    <div className={cn("rounded-lg p-3 pl-5", TG_CHAT_BG)}>
      <TelegramBubble
        tgHtml={tgHtml}
        imageUrl={imageUrl}
        channelName={channelName}
        withCitations={withCitations}
      />
    </div>
  );
}

/** Хвостик пузыря снизу слева, как в приложениях Telegram. */
function Tail() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 11 20"
      className="absolute bottom-0 -left-[9px] h-5 w-[11px] fill-white dark:fill-[#182533]"
    >
      <path d="M11 0v20H1.5c-1 0-1.4-1.2-.7-1.8C5.6 14.4 9.6 9.6 11 0z" />
    </svg>
  );
}

/** Фото поста: одно — во всю ширину, альбом — сеткой как в Telegram. */
function Album({ urls }: { urls: string[] }) {
  if (urls.length === 1)
    return (
      <img src={urls[0]} alt="" loading="lazy" className="max-h-[28rem] w-full object-cover" />
    );
  return (
    <div className="grid grid-cols-6 gap-0.5">
      {urls.slice(0, 10).map((u, i) => (
        <img
          key={u}
          src={u}
          alt=""
          loading="lazy"
          className={cn(
            "h-full w-full object-cover",
            // первое фото нечётного альбома — во всю ширину, остальные по два/три в ряд
            urls.length % 2 === 1 && i === 0
              ? "col-span-6 aspect-[16/10]"
              : urls.length > 4 && i > 0
                ? "col-span-2 aspect-square"
                : "col-span-3 aspect-square",
          )}
        />
      ))}
    </div>
  );
}

/** Одно сообщение канала: имя, медиа, текст, дополнения, подвал (время). Без фона чата. */
export function TelegramBubble({
  tgHtml,
  imageUrl,
  images,
  media,
  channelName,
  top,
  extra,
  withCitations = false,
  footer,
  tail = true,
  className,
}: {
  tgHtml: string;
  imageUrl: string | null;
  images?: string[];
  media?: ReactNode; // своё медиа вместо фото (видео, стикер, файл)
  channelName: string;
  top?: ReactNode; // над текстом: «Переслано из…»
  extra?: ReactNode; // под текстом: превью ссылки, реакции
  withCitations?: boolean;
  footer?: ReactNode;
  tail?: boolean;
  className?: string;
}) {
  const { t } = useTranslation("common");
  const [imageOk, setImageOk] = useState(true);
  const html = useMemo(() => toDisplayHtml(tgHtml, { withCitations }), [tgHtml, withCitations]);
  const reveal = (e: MouseEvent | KeyboardEvent) => {
    const el = (e.target as HTMLElement).closest(".tg-spoiler");
    if (el && (!("key" in e) || e.key === "Enter" || e.key === " "))
      el.classList.add("tg-spoiler--open");
  };
  const photos = images?.length ? images : imageUrl && imageOk ? [imageUrl] : [];
  const text = tgHtml.trim();
  return (
    <div
      role="article"
      aria-label={t("telegram.preview_label")}
      className={cn("relative w-fit max-w-[420px] min-w-[7rem]", className)}
    >
      {tail ? <Tail /> : null}
      <div
        className={cn(
          "overflow-hidden rounded-xl bg-white text-[15px] leading-[1.35] text-black shadow-[0_1px_2px_rgb(16_35_47/0.15)] dark:bg-[#182533] dark:text-white",
          tail && "rounded-bl-none",
        )}
      >
        {channelName ? (
          <div className="px-3 pt-2 text-sm font-semibold text-[#3390ec]">{channelName}</div>
        ) : null}
        {top ? <div className="px-3 pt-1.5 text-sm text-[#3390ec]">{top}</div> : null}
        {media ??
          (photos.length ? (
            <div className={cn(channelName || top ? "mt-1.5" : "")}>
              {photos.length === 1 && !images?.length ? (
                <img
                  src={photos[0]}
                  alt=""
                  loading="lazy"
                  className="max-h-[28rem] w-full object-cover"
                  onError={() => setImageOk(false)}
                />
              ) : (
                <Album urls={photos} />
              )}
            </div>
          ) : null)}
        <div className="px-3 pt-1.5 pb-1.5 [overflow-wrap:anywhere]">
          {text ? (
            // eslint-disable-next-line jsx-a11y/no-static-element-interactions -- делегирование для spoiler-кнопок внутри
            <div
              className="tg-body [&_.tg-hashtag]:text-[#3390ec] [&_.tg-spoiler:not(.tg-spoiler--open)]:bg-slate-400 [&_.tg-spoiler:not(.tg-spoiler--open)]:text-transparent [&_.tg-spoiler:not(.tg-spoiler--open)]:blur-[3px] [&_a]:text-[#3390ec] dark:[&_a]:text-[#6ab3f3]"
              onClick={reveal}
              onKeyDown={reveal}
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : photos.length || media ? null : (
            <p className="text-muted-foreground italic">{t("telegram.empty")}</p>
          )}
          {extra}
          <div className="float-right mt-1 -mb-0.5 ml-3 flex items-center gap-1 text-xs text-[#a0acb6] dark:text-[#6d7f8f]">
            {footer ?? (
              <>
                <EyeIcon aria-hidden className="size-3.5" />— · 12:00
              </>
            )}
          </div>
          <div className="clear-both" />
        </div>
      </div>
    </div>
  );
}
