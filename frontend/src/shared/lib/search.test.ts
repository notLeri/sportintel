import {
  parseEnumList,
  parseIso,
  parseList,
  parsePeriod,
  parseSearchString,
  parseUuid,
  stringifySearchObject,
} from "./search";

test.each([
  [undefined, []],
  ["football", ["football"]],
  ["football,tennis", ["football", "tennis"]],
  [
    ["football", "tennis,mma"],
    ["football", "tennis", "mma"],
  ],
  [" a , ,b ", ["a", "b"]],
  [{ x: 1 }, []],
])("parseList(%j)", (raw, expected) => {
  expect(parseList(raw)).toEqual(expected);
});

test("parseEnumList drops unknown values and duplicates", () => {
  expect(parseEnumList("HIGH,bogus,LOW,HIGH", ["HIGH", "MEDIUM", "LOW"] as const)).toEqual([
    "HIGH",
    "LOW",
  ]);
});

test.each([
  ["2026-10-07", "2026-10-07"],
  ["2026-10-07T12:30:00Z", "2026-10-07T12:30:00Z"],
  ["2026-10-07T12:30:00-03:00", "2026-10-07T12:30:00-03:00"],
  ["2026-13-40", undefined],
  ["yesterday", undefined],
  [42, undefined],
])("parseIso(%j)", (raw, expected) => {
  expect(parseIso(raw)).toBe(expected);
});

test.each([
  ["6h", "6h"],
  ["custom", "custom"],
  ["1y", "24h"],
  [undefined, "24h"],
])("parsePeriod(%j)", (raw, expected) => {
  expect(parsePeriod(raw)).toBe(expected);
});

test("parseUuid normalizes case and rejects garbage", () => {
  expect(parseUuid("0192F6A1-0000-7000-8000-000000000001")).toBe(
    "0192f6a1-0000-7000-8000-000000000001",
  );
  expect(parseUuid("not-a-uuid")).toBeUndefined();
});

test("search string round-trip keeps commas readable", () => {
  const s = stringifySearchObject({ sport: ["football", "tennis"], q: "São Paulo", empty: [] });
  expect(s).toBe("?sport=football,tennis&q=S%C3%A3o+Paulo");
  expect(parseSearchString(s)).toEqual({ sport: "football,tennis", q: "São Paulo" });
  expect(parseSearchString("?a=1&a=2")).toEqual({ a: ["1", "2"] });
});
