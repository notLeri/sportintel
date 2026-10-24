import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { EventFlags, RelevanceBadge } from "./badges";

const FLAGS = {
  has_open_conflicts: false,
  stale_suspected: true,
  has_clickbait: true,
  has_updates_since_edit: false,
};

test("stale and clickbait badges carry text and explanatory tooltip", async () => {
  render(<EventFlags e={FLAGS} />);
  await userEvent.hover(screen.getByText("Possivelmente antiga"));
  expect(await screen.findByRole("tooltip")).toHaveTextContent("evento antigo semelhante");
});

test("relevance badge explains the metric and the level on hover", async () => {
  render(<RelevanceBadge level="HIGH" />);
  await userEvent.hover(screen.getByText("Relevância alta"));
  expect(await screen.findByRole("tooltip")).toHaveTextContent(/Relevância.*vale publicar/);
});
