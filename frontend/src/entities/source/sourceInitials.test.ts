import { expect, test } from "vitest";

import { sourceInitials } from "./sourceInitials";

test("source initials stay short and readable", () => {
  expect(sourceInitials("ge (Globo Esporte)")).toBe("GE");
  expect(sourceInitials("CNN Brasil")).toBe("CNN");
  expect(sourceInitials("Матч ТВ (Telegram)")).toBe("МТ");
  expect(sourceInitials("Россия — праздники")).toBe("РП");
  expect(sourceInitials("Winline (Telegram)")).toBe("WI");
});
