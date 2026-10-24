import { useEffect, useRef } from "react";

const EDITABLE = "input, textarea, select, [contenteditable=''], [contenteditable='true']";

export function isEditableTarget(t: EventTarget | null): boolean {
  return t instanceof Element && Boolean(t.closest(EDITABLE));
}

/** Горячая клавиша без модификаторов; не срабатывает в полях ввода и при enabled=false (me.hotkeys_enabled). */
export function useHotkey(
  key: string,
  handler: (e: KeyboardEvent) => void,
  { enabled = true } = {},
) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== key || e.ctrlKey || e.metaKey || e.altKey || isEditableTarget(e.target)) return;
      ref.current(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [key, enabled]);
}
