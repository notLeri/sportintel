import { Extension } from "@tiptap/react";
import type { Node as PMNode } from "@tiptap/pm/model";
import { Plugin, PluginKey } from "@tiptap/pm/state";
import { Decoration, DecorationSet } from "@tiptap/pm/view";

export interface DecorationOptions {
  onCitationClick?: (n: number) => void;
  /** Тексты непроверенных предложений (grounding ≠ ok, только версия origin=ai). */
  unverified: { text: string; title: string }[];
}

const norm = (s: string) =>
  s
    .replace(/\s?\[\d{1,2}\]/g, "")
    .replace(/\s+/g, " ")
    .trim();

function build(doc: PMNode, opts: DecorationOptions): DecorationSet {
  const decos: Decoration[] = [];
  doc.descendants((node, pos) => {
    if (!node.isText || !node.text) return;
    for (const m of node.text.matchAll(/\[(\d{1,2})\]/g)) {
      decos.push(
        Decoration.inline(pos + m.index, pos + m.index + m[0].length, {
          class: "citation",
          "data-n": m[1] ?? "",
        }),
      );
    }
  });
  if (opts.unverified.length) {
    doc.descendants((node, pos) => {
      if (!node.isTextblock) return;
      const text = node.textContent;
      for (const u of opts.unverified) {
        const needle = norm(u.text);
        const i = needle ? norm(text).indexOf(needle) : -1;
        // ponytail: позиция по нормализованному тексту приблизительна при множественных пробелах — для подсветки достаточно.
        if (i >= 0)
          decos.push(
            Decoration.inline(pos + 1 + i, pos + 1 + i + needle.length, {
              class: "unverified",
              title: u.title,
            }),
          );
      }
    });
  }
  return DecorationSet.create(doc, decos);
}

export const DraftDecorations = Extension.create<DecorationOptions>({
  name: "draftDecorations",
  addOptions: () => ({ unverified: [], onCitationClick: undefined }),
  addProseMirrorPlugins() {
    const opts = this.options;
    return [
      new Plugin({
        key: new PluginKey("draftDecorations"),
        props: {
          decorations: (state) => build(state.doc, opts),
          handleClick: (_view, _pos, event) => {
            const el = (event.target as HTMLElement).closest(".citation");
            if (!el) return false;
            opts.onCitationClick?.(Number(el.getAttribute("data-n")));
            return true;
          },
        },
      }),
    ];
  },
});
