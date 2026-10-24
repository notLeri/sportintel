const LETTER = /\p{L}/gu;
const CYRILLIC = /[а-яё]/giu;
const PT_MARKS = /[ãõçâêôáéíóúà]/iu;

/** Похоже ли, что текст уже на языке интерфейса (без вызова ИИ — по алфавиту).
 * ponytail: грубая эвристика ru/en; для точности — язык из данных статьи. */
export function looksLike(text: string, lang: string): boolean {
  const letters = text.match(LETTER) ?? [];
  if (!letters.length) return true;
  const cyr = (text.match(CYRILLIC) ?? []).length / letters.length;
  if (lang.startsWith("ru")) return cyr >= 0.6;
  if (lang.startsWith("en")) return cyr < 0.2 && !PT_MARKS.test(text);
  return true;
}
