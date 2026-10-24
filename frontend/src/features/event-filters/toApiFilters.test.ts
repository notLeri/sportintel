import { activeFiltersCount, periodError, toApiFilters } from "./toApiFilters";

const NOW = new Date("2026-10-08T12:00:00Z");

test("defaults", () => {
  expect(toApiFilters({}, NOW)).toEqual({
    sport: undefined,
    competition: undefined,
    relevance: ["HIGH", "MEDIUM", "LOW"],
    reliability: undefined,
    source: undefined,
    status: ["NEW", "REVIEWING", "SELECTED", "DRAFT", "READY"],
    entity: undefined,
    conflicts: undefined,
    q: undefined,
    sort: "rank",
    from: "2026-10-07T12:00:00.000Z",
  });
  expect(activeFiltersCount({})).toBe(0);
});

test("period slides with now; custom uses from/to; conflicts", () => {
  expect(toApiFilters({ period: "1h" }, NOW).from).toBe("2026-10-08T11:00:00.000Z");
  const later = new Date(NOW.getTime() + 60_000);
  expect(toApiFilters({ period: "1h" }, later).from).toBe("2026-10-08T11:01:00.000Z");
  const c = toApiFilters(
    { period: "custom", from: "2026-10-01T00:00:00Z", to: "2026-10-02T00:00:00Z", conflicts: "1" },
    NOW,
  );
  expect([c.from, c.to, c.conflicts]).toEqual([
    "2026-10-01T00:00:00Z",
    "2026-10-02T00:00:00Z",
    true,
  ]);
  expect(
    periodError({ period: "custom", from: "2026-10-03T00:00:00Z", to: "2026-10-02T00:00:00Z" }),
  ).toBe(true);
});

test("active count ignores defaults and counts empty relevance", () => {
  expect(activeFiltersCount({ relevance: ["LOW", "MEDIUM", "HIGH"] })).toBe(0);
  expect(activeFiltersCount({ relevance: [], sport: ["football"], period: "7d" })).toBe(3);
  expect(toApiFilters({ relevance: [] }, NOW).relevance).toEqual([]);
});
