import { stripCitations } from "./citations";
import { sanitize } from "./sanitize";

const HASHTAG = /#[0-9A-Za-zÀ-ÿ_]{2,30}/g;

/** Хэштеги — только в текстовых узлах вне ссылок (FE-T3.10 §22). */
function wrapHashtags(root: HTMLElement) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    if (!(n.parentElement?.closest("a") ?? null)) nodes.push(n as Text);
  }
  for (const node of nodes) {
    const text = node.data;
    if (!HASHTAG.test(text)) continue;
    HASHTAG.lastIndex = 0;
    const frag = document.createDocumentFragment();
    let last = 0;
    for (const m of text.matchAll(HASHTAG)) {
      frag.append(text.slice(last, m.index));
      const span = document.createElement("span");
      span.className = "tg-hashtag";
      span.textContent = m[0];
      frag.append(span);
      last = m.index + m[0].length;
    }
    frag.append(text.slice(last));
    node.replaceWith(frag);
  }
}

export function toDisplayHtml(
  tgHtml: string,
  { withCitations }: { withCitations: boolean },
): string {
  let html = sanitize(tgHtml);
  if (!withCitations) html = stripCitations(html);
  const root = document.createElement("div");
  root.innerHTML = html.replace(/\n/g, "<br>");
  for (const s of root.querySelectorAll("tg-spoiler")) {
    const span = document.createElement("span");
    span.className = "tg-spoiler";
    span.setAttribute("tabindex", "0");
    span.setAttribute("role", "button");
    span.setAttribute("aria-label", "Spoiler");
    span.append(...s.childNodes);
    s.replaceWith(span);
  }
  for (const a of root.querySelectorAll("a")) {
    a.setAttribute("target", "_blank");
    a.setAttribute("rel", "noopener noreferrer");
  }
  wrapHashtags(root);
  return root.innerHTML;
}
