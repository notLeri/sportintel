import { can } from "./can";
import type { Permission } from "./types";

const researcher: Permission[] = ["self.read", "events.read", "drafts.write"];

test("can() reflects me.permissions", () => {
  expect(can({ permissions: researcher }, "events.read")).toBe(true);
  expect(can({ permissions: researcher }, "users.manage")).toBe(false);
});

test("can() is false without a user", () => {
  expect(can(null, "events.read")).toBe(false);
  expect(can(undefined, "self.read")).toBe(false);
});
