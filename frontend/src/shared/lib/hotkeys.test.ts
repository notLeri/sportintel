import { renderHook } from "@testing-library/react";

import { useHotkey } from "./hotkeys";

function press(key: string, target: EventTarget = window) {
  target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
}

test("fires outside inputs, ignored inside inputs and when disabled", () => {
  const fn = vi.fn();
  const { rerender } = renderHook(({ enabled }) => useHotkey("j", fn, { enabled }), {
    initialProps: { enabled: true },
  });
  press("j");
  expect(fn).toHaveBeenCalledTimes(1);
  const input = document.createElement("input");
  document.body.append(input);
  press("j", input);
  expect(fn).toHaveBeenCalledTimes(1);
  rerender({ enabled: false });
  press("j");
  expect(fn).toHaveBeenCalledTimes(1);
  input.remove();
});
