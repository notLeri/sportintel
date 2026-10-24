// Локальный буфер несохранённых правок черновика (FE-T3.12). localStorage может быть недоступен.

export interface DraftBuffer {
  tgHtml: string;
  imageUrl: string | null;
  savedAt: string;
}

const PREFIX = "draft:";

export function bufferKey(draftId: string, baseVersion: number): string {
  return `${PREFIX}${draftId}:${baseVersion}`;
}

export function saveBuffer(key: string, value: DraftBuffer): void {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* приватный режим или квота — правки остаются только в памяти */
  }
}

function keysFor(draftId: string): string[] {
  try {
    return Object.keys(localStorage).filter((k) => k.startsWith(`${PREFIX}${draftId}:`));
  } catch {
    return [];
  }
}

export function loadBuffer(draftId: string): { key: string; value: DraftBuffer } | null {
  let best: { key: string; value: DraftBuffer } | null = null;
  for (const key of keysFor(draftId)) {
    try {
      const value = JSON.parse(localStorage.getItem(key) ?? "null") as DraftBuffer | null;
      if (value && (!best || value.savedAt > best.value.savedAt)) best = { key, value };
    } catch {
      /* битая запись игнорируется */
    }
  }
  return best;
}

export function clearBuffers(draftId: string): void {
  for (const key of keysFor(draftId)) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* нет доступа */
    }
  }
}
