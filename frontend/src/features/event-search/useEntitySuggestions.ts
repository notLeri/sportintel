import { useEffect, useState } from "react";

import { useEntitySearch } from "@/entities/taxonomy";

export const SUGGEST_DEBOUNCE_MS = 300;
export const MAX_SUGGESTIONS = 8;

/** Подсказки сущностей с debounce. ponytail: без AbortSignal — jsdom/undici несовместимы; кэш по ключу гасит лишнее. */
export function useEntitySuggestions(text: string) {
  const [term, setTerm] = useState(text);
  useEffect(() => {
    const id = setTimeout(() => setTerm(text), SUGGEST_DEBOUNCE_MS);
    return () => clearTimeout(id);
  }, [text]);
  const q = useEntitySearch(term);
  return { items: q.isError ? [] : (q.data ?? []).slice(0, MAX_SUGGESTIONS) };
}
