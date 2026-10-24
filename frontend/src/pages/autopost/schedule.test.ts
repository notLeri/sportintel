import { fromLocalInput, groupByDay, toLocalInput, zonedToUtc } from "./schedule";

test("groups UTC slots by the user's day and counts queued posts", () => {
  const now = new Date("2026-10-10T20:00:00Z"); // 23:00 в Москве
  const runs = ["2026-10-10T20:30:00Z", "2026-10-10T21:30:00Z", "2026-10-11T06:00:00Z"];
  const queue = [{ run_at: runs[0] as string }, { run_at: runs[0] as string }];
  const days = groupByDay(runs, queue, now, "Europe/Moscow", 3);
  expect(days.map((d) => d.key)).toEqual(["2026-10-10", "2026-10-11", "2026-10-12"]);
  // 21:30 UTC — уже 00:30 следующего дня по Москве
  expect(days[0]?.slots).toEqual([{ at: runs[0], posts: 2 }]);
  expect(days[1]?.slots.map((s) => s.at)).toEqual([runs[1], runs[2]]);
  expect(days[2]?.slots).toEqual([]);
});

test("wall time in the user's zone converts to UTC and back", () => {
  expect(zonedToUtc("2026-10-12", 14, 30, "Europe/Moscow")).toBe("2026-10-12T11:30:00.000Z");
  expect(zonedToUtc("2026-10-12", 9, 0, "America/Sao_Paulo")).toBe("2026-10-12T12:00:00.000Z");
  // Нью-Йорк: летнее время кончается 1 ноября 2026
  expect(zonedToUtc("2026-11-02", 9, 0, "America/New_York")).toBe("2026-11-02T14:00:00.000Z");
  expect(toLocalInput("2026-10-12T11:30:00Z", "Europe/Moscow")).toBe("2026-10-12T14:30");
  expect(fromLocalInput("2026-10-12T14:30", "Europe/Moscow")).toBe("2026-10-12T11:30:00.000Z");
});
