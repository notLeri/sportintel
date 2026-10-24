export const CITATION_RE = /\s?\[\d{1,2}\]/g;

export function stripCitations(s: string): string {
  return s.replace(CITATION_RE, "");
}
