import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DateTimePicker } from "./date-time-picker";

test("day first, then time: value changes only when the time is picked; past is disabled", async () => {
  const onChange = vi.fn();
  render(
    <DateTimePicker
      label="Quando"
      value="2026-10-12T15:30"
      min="2026-10-11T14:05"
      today="2026-10-11"
      zoneLabel="Sao Paulo (GMT−3)"
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /^Quando:/ }));
  const grid = screen.getByRole("grid", { name: /outubro de 2026/i });
  const day = (d: string) =>
    within(grid)
      .getAllByRole("button")
      .find((b) => b.dataset.day === d) as HTMLButtonElement;
  expect(day("2026-10-10")).toBeDisabled(); // прошлое
  expect(day("2026-10-12").closest("[role=gridcell]")).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Horário — Sao Paulo (GMT−3)")).toBeInTheDocument();

  await userEvent.click(day("2026-10-11"));
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByRole("option", { name: "14:00" })).toBeDisabled(); // сегодня уже прошло
  await userEvent.click(screen.getByRole("option", { name: "14:15" }));
  expect(onChange).toHaveBeenCalledWith("2026-10-11T14:15");

  // следующий месяц — стрелкой
  await userEvent.click(screen.getByRole("button", { name: /^Quando:/ }));
  await userEvent.click(screen.getByRole("button", { name: "Próximo mês" }));
  expect(screen.getByRole("grid", { name: /novembro de 2026/i })).toBeInTheDocument();
});
