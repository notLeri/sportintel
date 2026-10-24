import { bufferKey, clearBuffers, loadBuffer, saveBuffer } from "./draft-autosave";

const v = (savedAt: string) => ({
  tgHtml: savedAt,
  imageUrl: null,
  savedAt,
});

afterEach(() => localStorage.clear());

test("keys, latest buffer and clearing", () => {
  expect(bufferKey("d1", 3)).toBe("draft:d1:3");
  saveBuffer(bufferKey("d1", 1), v("2026-10-09T10:00:00Z"));
  saveBuffer(bufferKey("d1", 2), v("2026-10-09T11:00:00Z"));
  saveBuffer(bufferKey("d2", 1), v("2026-10-09T12:00:00Z"));
  expect(loadBuffer("d1")?.value.tgHtml).toBe("2026-10-09T11:00:00Z");
  clearBuffers("d1");
  expect(loadBuffer("d1")).toBeNull();
  expect(loadBuffer("d2")).not.toBeNull();
});

test("unavailable localStorage does not throw", () => {
  const spy = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("denied");
  });
  expect(() => saveBuffer("draft:x:1", v("t"))).not.toThrow();
  spy.mockRestore();
});
