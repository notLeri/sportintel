import { splitCitations } from "./citations";

test("splits text and citation markers", () => {
  expect(splitCitations("Flamengo vence [1] e lidera [2][3].")).toEqual([
    { kind: "text", text: "Flamengo vence " },
    { kind: "cite", n: 1 },
    { kind: "text", text: " e lidera " },
    { kind: "cite", n: 2 },
    { kind: "cite", n: 3 },
    { kind: "text", text: "." },
  ]);
  expect(splitCitations("sem citações")).toEqual([{ kind: "text", text: "sem citações" }]);
});
