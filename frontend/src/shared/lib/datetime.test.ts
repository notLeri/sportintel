import { i18n } from "@/shared/i18n";

import { formatDateTime, formatRelative, periodToRange } from "./datetime";

const NOW = new Date("2026-10-08T12:00:00Z");

test.each([
  ["1h", "2026-10-08T11:00:00.000Z"],
  ["6h", "2026-10-08T06:00:00.000Z"],
  ["24h", "2026-10-07T12:00:00.000Z"],
  ["7d", "2026-10-01T12:00:00.000Z"],
] as const)("periodToRange(%s)", (period, from) => {
  expect(periodToRange(period, NOW)).toEqual({ from });
});

test("custom period uses explicit bounds", () => {
  expect(periodToRange("custom", NOW, { from: "2026-10-01", to: "2026-10-02" })).toEqual({
    from: "2026-10-01",
    to: "2026-10-02",
  });
});

test("formatDateTime uses the user's time zone", () => {
  expect(formatDateTime("2026-10-08T12:00:00Z", "America/Sao_Paulo", "pt-BR")).toBe(
    "08/10/2026, 09:00",
  );
  expect(formatDateTime(null, "UTC")).toBe("—");
});

test("formatRelative", () => {
  expect(formatRelative("2026-10-08T10:00:00Z", NOW, "pt-BR")).toBe("há 2 horas");
});

test("default locale follows the UI language", async () => {
  await i18n.changeLanguage("ru");
  expect(formatRelative("2026-10-08T10:00:00Z", NOW)).toBe("2 часа назад");
  await i18n.changeLanguage("en");
  expect(formatRelative("2026-10-08T10:00:00Z", NOW)).toBe("2 hours ago");
});
