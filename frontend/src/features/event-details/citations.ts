export type SummaryPart = { kind: "text"; text: string } | { kind: "cite"; n: number };

/** «Texto [1] mais [2].» → части текста и ссылки-цитаты. */
export function splitCitations(text: string): SummaryPart[] {
  const parts: SummaryPart[] = [];
  let last = 0;
  for (const m of text.matchAll(/\[(\d+)\]/g)) {
    if (m.index > last) parts.push({ kind: "text", text: text.slice(last, m.index) });
    parts.push({ kind: "cite", n: Number(m[1]) });
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push({ kind: "text", text: text.slice(last) });
  return parts;
}
