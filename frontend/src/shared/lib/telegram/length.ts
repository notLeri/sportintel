import { stripCitations } from "./citations";

/** Как BE limits.plain_length: без тегов и [n], сущности раскодированы. */
export function plainLength(tgHtml: string): number {
  const doc = new DOMParser().parseFromString(
    `<body>${stripCitations(tgHtml).replace(/<[^>]+>/g, "")}</body>`,
    "text/html",
  );
  return (doc.body.textContent ?? "").length;
}
