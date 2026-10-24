import type { JSONContent } from "@tiptap/react";

import { sanitize } from "@/shared/lib/telegram";

type Mark = { type: string; attrs?: Record<string, unknown> };
type Piece = JSONContent | "para";

const MARKS: Record<string, string> = {
  b: "bold",
  strong: "bold",
  i: "italic",
  em: "italic",
  u: "underline",
  ins: "underline",
  s: "strike",
  strike: "strike",
  del: "strike",
  code: "code",
  a: "link",
  "tg-spoiler": "spoiler",
};

function inline(node: Node, marks: Mark[], out: Piece[]) {
  if (node.nodeType === Node.TEXT_NODE) {
    const parts = (node.textContent ?? "").split(/(\n\n+|\n)/);
    for (const p of parts) {
      if (!p) continue;
      if (p.startsWith("\n\n")) out.push("para");
      else if (p === "\n") out.push({ type: "hardBreak" });
      else out.push(marks.length ? { type: "text", text: p, marks } : { type: "text", text: p });
    }
    return;
  }
  if (!(node instanceof Element)) return;
  const tag = node.tagName.toLowerCase();
  const kind = MARKS[tag];
  const next = kind
    ? [
        ...marks,
        kind === "link"
          ? { type: "link", attrs: { href: node.getAttribute("href") ?? "" } }
          : { type: kind },
      ]
    : marks;
  for (const c of node.childNodes) inline(c, next, out);
}

function paragraphs(pieces: Piece[]): JSONContent[] {
  const paras: JSONContent[] = [];
  let cur: JSONContent[] = [];
  const flush = () => {
    paras.push(cur.length ? { type: "paragraph", content: cur } : { type: "paragraph" });
    cur = [];
  };
  for (const p of pieces) {
    if (p === "para") flush();
    else cur.push(p);
  }
  if (cur.length || !paras.length) flush();
  return paras;
}

/** Telegram HTML → документ Tiptap (FE-T3.11 §7). Вход санитизируется. */
export function tgToDoc(tgHtml: string): JSONContent {
  const root = document.createElement("div");
  root.innerHTML = sanitize(tgHtml);
  const blocks: JSONContent[] = [];
  let pending: Piece[] = [];
  const flushInline = () => {
    if (pending.some((p) => p !== "para"))
      blocks.push(...paragraphs(pending).filter((p) => p.content));
    pending = [];
  };
  for (const node of root.childNodes) {
    const tag = node instanceof Element ? node.tagName.toLowerCase() : "";
    if (tag === "pre") {
      flushInline();
      const text = node.textContent ?? "";
      blocks.push(
        text ? { type: "codeBlock", content: [{ type: "text", text }] } : { type: "codeBlock" },
      );
    } else if (tag === "blockquote") {
      flushInline();
      const inner: Piece[] = [];
      for (const c of node.childNodes) inline(c, [], inner);
      blocks.push({ type: "blockquote", content: paragraphs(inner) });
    } else {
      inline(node, [], pending);
    }
  }
  flushInline();
  return { type: "doc", content: blocks.length ? blocks : [{ type: "paragraph" }] };
}
