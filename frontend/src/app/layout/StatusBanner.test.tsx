import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const status = (extra: object) => ({
  ai: { mode: "rules", llm: { configured: false, available: false, model: null } },
  sources_down: 0,
  pipeline_delayed: false,
  ...extra,
});

afterEach(() => sessionStorage.clear());

test("nothing to say → no banner", async () => {
  mockMe(makeMe("admin", { system_status: status({}) }));
  renderApp("/articles");
  await screen.findByRole("heading", { name: "Artigos" });
  expect(screen.queryByRole("status", { name: "" })?.textContent ?? "").not.toMatch(
    /indisponíve|atraso/,
  );
});

test("LM offline is informational; sources down links admins; dismiss persists per status", async () => {
  mockMe(
    makeMe("admin", {
      system_status: status({
        ai: { mode: "mixed", llm: { configured: true, available: false, model: "qwen" } },
        sources_down: 2,
        pipeline_delayed: true,
      }),
    }),
  );
  renderApp("/articles");
  const banner = await screen.findByText("LM indisponível — usando regras");
  const box = banner.closest('[role="status"]') as HTMLElement;
  expect(box).toHaveTextContent("2 fontes indisponíveis");
  expect(box).toHaveTextContent("Novas notícias podem chegar com atraso");
  expect(screen.getByRole("link", { name: "Ver fontes" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Fechar aviso" }));
  await waitFor(() =>
    expect(screen.queryByText("LM indisponível — usando regras")).not.toBeInTheDocument(),
  );
});
