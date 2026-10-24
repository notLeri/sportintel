import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { Button } from "./button";

test("renders and handles click", async () => {
  const onClick = vi.fn();
  render(<Button onClick={onClick}>Salvar</Button>);
  await userEvent.click(screen.getByRole("button", { name: "Salvar" }));
  expect(onClick).toHaveBeenCalledOnce();
});
