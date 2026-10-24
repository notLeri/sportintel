import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";

import { sanitize } from "@/shared/lib/telegram";

import { docToTg } from "./convert/docToTg";
import { tgToDoc } from "./convert/tgToDoc";
import { DraftDecorations } from "./extensions/decorations";
import { Spoiler } from "./extensions/spoiler";
import { Toolbar } from "./Toolbar";

export interface UnverifiedSentence {
  text: string;
  title: string;
}

/** WYSIWYG в пределах Telegram HTML (FE-T3.11). Значение — Telegram HTML в формате BE-T3.8. */
export function DraftEditor({
  value,
  onChange,
  onCitationClick,
  unverified = [],
  readOnly = false,
  label,
}: {
  value: string;
  onChange: (tgHtml: string) => void;
  onCitationClick?: (n: number) => void;
  unverified?: UnverifiedSentence[];
  readOnly?: boolean;
  label?: string;
}) {
  const { t } = useTranslation("event");
  const last = useRef(value);
  const editor = useEditor({
    immediatelyRender: true,
    shouldRerenderOnTransaction: true, // тулбар отражает активные marks (в Tiptap 3 по умолчанию выключено)
    editable: !readOnly,
    extensions: [
      // Telegram не поддерживает заголовки, списки и горизонтальную линию (§22). В Tiptap 3 link и underline — в StarterKit.
      StarterKit.configure({
        heading: false,
        bulletList: false,
        orderedList: false,
        listItem: false,
        listKeymap: false,
        horizontalRule: false,
        trailingNode: false,
        link: { openOnClick: false, autolink: false, protocols: ["http", "https"] },
      }),
      Spoiler,
      DraftDecorations.configure({ onCitationClick, unverified }),
    ],
    content: tgToDoc(value),
    editorProps: {
      attributes: {
        role: "textbox",
        "aria-multiline": "true",
        "aria-label": label ?? t("draft.editor"),
        class: "min-h-40 rounded-md border p-3 text-[15px] outline-none",
      },
      transformPastedHTML: (html) => sanitize(html),
    },
    onUpdate: ({ editor: e }) => {
      const next = docToTg(e.getJSON());
      // Нормализация HTML редактором при загрузке — не правка: иначе черновик «грязный» без изменений.
      if (next === docToTg(tgToDoc(last.current))) return;
      last.current = next;
      onChange(next);
    },
  });
  useEffect(() => {
    // Внешняя смена значения (восстановление, другая версия) — без зацикливания на собственных правках.
    if (editor && value !== last.current) {
      last.current = value;
      editor.commands.setContent(tgToDoc(value), { emitUpdate: false });
    }
  }, [editor, value]);
  useEffect(() => editor?.setEditable(!readOnly), [editor, readOnly]);
  return (
    <div className="space-y-2 [&_.citation]:cursor-pointer [&_.citation]:bg-ai/15 [&_.tg-spoiler-edit]:bg-muted-foreground/30 [&_.unverified]:underline [&_.unverified]:decoration-warn [&_.unverified]:decoration-wavy">
      {editor && !readOnly ? <Toolbar editor={editor} /> : null}
      <EditorContent editor={editor} />
    </div>
  );
}
