import type { JSONContent } from "@tiptap/react";

// Порядок вложенности marks: снаружи link, внутри code (FE-T3.11 §7).
const ORDER = ["link", "bold", "italic", "underline", "strike", "spoiler", "code"] as const;
const TAG: Record<string, string> = {
  bold: "b",
  italic: "i",
  underline: "u",
  strike: "s",
  spoiler: "tg-spoiler",
  code: "code",
};

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

function markOf(n: JSONContent, type: string) {
  return n.marks?.find((m) => m.type === type);
}

function key(n: JSONContent, type: string): string | null {
  const m = markOf(n, type);
  if (!m) return null;
  return type === "link" ? `link:${String(m.attrs?.href ?? "")}` : type;
}

function serialize(nodes: JSONContent[], level: number): string {
  if (level === ORDER.length)
    return nodes.map((n) => (n.type === "hardBreak" ? "\n" : esc(n.text ?? ""))).join("");
  const type = ORDER[level] as string;
  let out = "";
  let i = 0;
  while (i < nodes.length) {
    const k = key(nodes[i] as JSONContent, type);
    let j = i + 1;
    while (
      j < nodes.length &&
      key(nodes[j] as JSONContent, type) === k &&
      (nodes[j] as JSONContent).type !== "hardBreak"
    )
      j++;
    const run = nodes.slice(i, j);
    const inner = serialize(run, level + 1);
    if (k === null) out += inner;
    else if (type === "link")
      out += `<a href="${esc(String(markOf(run[0] as JSONContent, "link")?.attrs?.href ?? "")).replace(/"/g, "&quot;")}">${inner}</a>`;
    else out += `<${TAG[type]}>${inner}</${TAG[type]}>`;
    i = j;
  }
  return out;
}

function block(n: JSONContent): string {
  if (n.type === "codeBlock")
    return `<pre>${esc((n.content ?? []).map((c) => c.text ?? "").join(""))}</pre>`;
  if (n.type === "blockquote")
    return `<blockquote>${(n.content ?? []).map(block).join("\n\n")}</blockquote>`;
  return serialize(n.content ?? [], 0);
}

/** Документ Tiptap → Telegram HTML (формат BE-T3.8). */
export function docToTg(doc: JSONContent): string {
  return (doc.content ?? [])
    .map(block)
    .join("\n\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
