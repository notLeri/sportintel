import { regionName } from "./region";

test("country name follows the UI language", () => {
  expect(regionName("BR", "ru")).toBe("Бразилия");
  expect(regionName("PT", "en")).toBe("Portugal");
  expect(regionName("??", "en")).toBe("??");
});
