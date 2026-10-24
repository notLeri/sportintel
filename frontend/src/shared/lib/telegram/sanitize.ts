import DOMPurify from "dompurify";

// Как BE-T3.8: подмножество Telegram HTML; ссылки только http(s).
export const ALLOWED_TAGS = [
  "b",
  "strong",
  "i",
  "em",
  "u",
  "ins",
  "s",
  "strike",
  "del",
  "a",
  "code",
  "pre",
  "blockquote",
  "tg-spoiler",
];

export function sanitize(tgHtml: string): string {
  return DOMPurify.sanitize(tgHtml, {
    ALLOWED_TAGS,
    ALLOWED_ATTR: ["href"],
    ALLOWED_URI_REGEXP: /^https?:/i,
    CUSTOM_ELEMENT_HANDLING: { tagNameCheck: /^tg-spoiler$/, attributeNameCheck: () => false },
  });
}
