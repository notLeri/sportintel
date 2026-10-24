import type { Editor } from "@tiptap/react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button, Input, Popover, PopoverContent, PopoverTrigger } from "@/shared/ui";

export function Toolbar({ editor }: { editor: Editor }) {
  const { t } = useTranslation("event");
  const [url, setUrl] = useState("");
  const [linkOpen, setLinkOpen] = useState(false);
  const valid = /^https?:\/\/\S+$/i.test(url.trim());
  const btn = (name: string, label: string, run: () => void, keys?: string) => (
    <Button
      key={name}
      type="button"
      size="sm"
      variant={editor.isActive(name) ? "default" : "ghost"}
      aria-pressed={editor.isActive(name)}
      aria-keyshortcuts={keys}
      title={keys ? `${label} (${keys})` : label}
      onClick={run}
    >
      {label}
    </Button>
  );
  const chain = () => editor.chain().focus();
  return (
    <div role="toolbar" aria-label={t("draft.toolbar")} className="flex flex-wrap gap-1">
      {btn("bold", t("draft.bold"), () => chain().toggleBold().run(), "Control+B")}
      {btn("italic", t("draft.italic"), () => chain().toggleItalic().run(), "Control+I")}
      {btn("underline", t("draft.underline"), () => chain().toggleUnderline().run(), "Control+U")}
      {btn("strike", t("draft.strike"), () => chain().toggleStrike().run())}
      <Popover open={linkOpen} onOpenChange={setLinkOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            size="sm"
            variant={editor.isActive("link") ? "default" : "ghost"}
            aria-pressed={editor.isActive("link")}
            aria-keyshortcuts="Control+K"
          >
            {t("draft.link")}
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-72 space-y-2">
          <Input
            aria-label="URL"
            placeholder="https://"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={Boolean(url) && !valid}
          />
          <Button
            size="sm"
            disabled={!valid}
            onClick={() => {
              chain().extendMarkRange("link").setLink({ href: url.trim() }).run();
              setLinkOpen(false);
            }}
          >
            {t("draft.apply")}
          </Button>
        </PopoverContent>
      </Popover>
      {btn("code", t("draft.code"), () => chain().toggleCode().run())}
      {btn("blockquote", t("draft.quote"), () => chain().toggleBlockquote().run())}
      {btn("spoiler", t("draft.spoiler"), () => chain().toggleSpoiler().run())}
      <Button
        type="button"
        size="sm"
        variant="ghost"
        aria-keyshortcuts="Control+Z"
        onClick={() => chain().undo().run()}
      >
        {t("draft.undo")}
      </Button>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        aria-keyshortcuts="Control+Shift+Z"
        onClick={() => chain().redo().run()}
      >
        {t("draft.redo")}
      </Button>
    </div>
  );
}
