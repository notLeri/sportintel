import { stripCitations } from "./citations";
import { sanitize } from "./sanitize";

/** Два формата для буфера: html (теги Telegram, без [n], spoiler как текст) и plain. */
export function buildClipboard(tgHtml: string): { html: string; plain: string } {
  const root = document.createElement("div");
  root.innerHTML = stripCitations(sanitize(tgHtml));
  for (const s of root.querySelectorAll("tg-spoiler")) s.replaceWith(...s.childNodes);
  const body = root.innerHTML.replace(/\n/g, "<br>");
  const html = body;
  for (const a of root.querySelectorAll("a")) {
    const text = a.textContent ?? "";
    const href = a.getAttribute("href") ?? "";
    a.replaceWith(text === href || !href ? text : `${text} (${href})`);
  }
  return { html, plain: root.textContent ?? "" };
}
