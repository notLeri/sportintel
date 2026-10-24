import { cleanup, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { makeMe, mockMe, renderApp } from "../../../tests/setup/render";

beforeEach(() => mockMe(makeMe("researcher")));

const relevanceBox = async (name: RegExp) =>
  within(await screen.findByRole("group", { name: "Relevância" })).getByRole("checkbox", { name });

test("unchecking levels writes relevance to URL; clear resets", async () => {
  const { router } = renderApp("/");
  await userEvent.click(await relevanceBox(/Média/));
  await userEvent.click(await relevanceBox(/Baixa/));
  await waitFor(() => expect(router.state.location.href).toBe("/?relevance=HIGH"));
  await userEvent.click(
    within(screen.getByRole("complementary", { name: "Filtros" })).getByRole("button", {
      name: "Limpar filtros",
    }),
  );
  await waitFor(() => expect(router.state.location.href).not.toContain("relevance"));
});

test("state restored from URL, empty relevance hint, custom period", async () => {
  const { router } = renderApp("/?relevance=&sport=none&conflicts=1");
  expect(await screen.findByText("Selecione pelo menos um nível")).toBeInTheDocument();
  expect(await screen.findByRole("checkbox", { name: "Sem classificação" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "Somente com conflitos" })).toBeChecked();
  expect(screen.getByRole("heading", { name: /Filtros \(3\)/ })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Personalizado" }));
  // выбор в календаре: сегодняшний день, 10:00 по Сан-Паулу = 13:00 UTC
  const today = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(
    new Date(),
  );
  await userEvent.click(await screen.findByRole("button", { name: "De" }));
  const grid = await screen.findByRole("grid");
  await userEvent.click(
    within(grid)
      .getAllByRole("button")
      .find((b) => b.dataset.day === today) as HTMLElement,
  );
  await userEvent.click(screen.getByRole("option", { name: "10:00" }));
  await waitFor(() =>
    expect(router.state.location.href).toMatch(
      new RegExp(`relevance=&.*period=custom.*from=${today}T13%3A00`),
    ),
  );
});

const SOURCE = { id: "0192f6a1-0000-7000-8000-0000000000aa", name: "CNN Brasil", region: "BR" };

test("source chip: first click includes, second excludes, third clears", async () => {
  server.use(http.get("*/api/v1/sources", () => HttpResponse.json({ items: [SOURCE] })));
  const { router } = renderApp("/");
  const chip = await screen.findByRole("button", { name: "CNN Brasil" });
  await userEvent.click(chip);
  await waitFor(() => expect(router.state.location.href).toContain(`source=${SOURCE.id}`));
  await userEvent.click(screen.getByRole("button", { name: "CNN Brasil" }));
  await waitFor(() => expect(router.state.location.href).toContain(`xsource=${SOURCE.id}`));
  expect(router.state.location.href).not.toMatch(/[?&]source=/);
  await userEvent.click(screen.getByRole("button", { name: /CNN Brasil — excluída/ }));
  await waitFor(() => expect(router.state.location.href).not.toContain("xsource"));
});

test("filters are remembered for the user and restored on the next visit", async () => {
  const first = renderApp("/");
  await userEvent.click(await screen.findByRole("checkbox", { name: "Sem classificação" }));
  await waitFor(() => expect(first.router.state.location.href).toContain("sport=none"));
  cleanup();
  const { router } = renderApp("/");
  await waitFor(() => expect(router.state.location.href).toContain("sport=none"));
});
