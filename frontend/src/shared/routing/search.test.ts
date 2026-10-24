import { validateDashboardSearch, validateLoginSearch, withDashboardDefaults } from "./search";

test("invalid values override raw ones with explicit undefined", () => {
  const s = validateLoginSearch({ next: "//evil.com", error: "auth.not_allowed" });
  expect("next" in s).toBe(true);
  expect(s.next).toBeUndefined();
  // Слияние TanStack: {...raw, ...validated} — сырое значение не выживает.
  expect({ next: "//evil.com", ...s }.next).toBeUndefined();
});

test("login next accepts only app-relative paths", () => {
  expect(validateLoginSearch({ next: "/events/1?x=1" }).next).toBe("/events/1?x=1");
  expect(validateLoginSearch({ next: "https://evil.com" }).next).toBeUndefined();
});

test("dashboard defaults are implicit", () => {
  const s = validateDashboardSearch({ relevance: "HIGH,bogus", sort: "rank", period: "24h" });
  expect(s.relevance).toEqual(["HIGH"]);
  expect(s.sort).toBeUndefined();
  expect(withDashboardDefaults(s).status).not.toContain("REJECTED");
});

describe("dashboard relevance=", () => {
  it("keeps an explicit empty relevance list", () => {
    expect(validateDashboardSearch({ relevance: "" }).relevance).toEqual([]);
    expect(validateDashboardSearch({}).relevance).toBeUndefined();
  });
});
