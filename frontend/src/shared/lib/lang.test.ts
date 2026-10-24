import { looksLike } from "./lang";

test("detects whether a headline is already in the interface language", () => {
  expect(looksLike("Фламенго уволил тренера", "ru")).toBe(true);
  expect(looksLike("Flamengo demite técnico", "ru")).toBe(false);
  expect(looksLike("Flamengo fires coach", "en")).toBe(true);
  expect(looksLike("Flamengo demite técnico após eliminação", "en")).toBe(false);
});
