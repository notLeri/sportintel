import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeMe, mockMe, renderApp } from "../../tests/setup/render";

beforeEach(() => mockMe(makeMe("editor")));

test("navigates between screens and back", async () => {
  const { history } = renderApp("/");
  expect(await screen.findByRole("heading", { name: "Eventos" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("link", { name: "Artigos" }));
  expect(await screen.findByRole("heading", { name: "Artigos" })).toBeInTheDocument();
  history.back();
  expect(await screen.findByRole("heading", { name: "Eventos" })).toBeInTheDocument();
});

test("unknown path shows 404", async () => {
  renderApp("/nao-existe");
  expect(await screen.findByRole("heading", { name: "Página não encontrada" })).toBeInTheDocument();
});

test("invalid search params are dropped from the URL", async () => {
  const { router } = renderApp("/?relevance=HIGH,bogus&sort=rank&period=zzz");
  await screen.findByRole("heading", { name: "Eventos" });
  await vi.waitFor(() => expect(router.state.location.searchStr).toBe("?relevance=HIGH"));
});
