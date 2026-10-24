import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const FLA = "0192f6a1-0000-7000-8000-0000000000f1";
const LIB = "0192f6a1-0000-7000-8000-0000000000f2";

beforeEach(() => {
  mockMe(makeMe("researcher"));
  server.use(
    http.get(apiUrl("/api/v1/taxonomy/entities"), ({ request }) => {
      const u = new URL(request.url);
      if (u.searchParams.get("ids"))
        return HttpResponse.json({
          items: u.searchParams
            .getAll("ids")
            .flatMap((i) => i.split(","))
            .includes(FLA)
            ? [
                {
                  id: FLA,
                  kind: "team",
                  name: "Flamengo",
                  sport_id: "football",
                  review_state: "approved",
                },
              ]
            : [],
        });
      return HttpResponse.json({
        items: [
          {
            id: FLA,
            kind: "team",
            name: "Flamengo",
            sport_id: "football",
            review_state: "approved",
          },
          {
            id: LIB,
            kind: "competition",
            name: "CONMEBOL Libertadores",
            sport_id: "football",
            review_state: "approved",
          },
        ],
      });
    }),
  );
});

const box = () => screen.findByRole("combobox", { name: "Buscar eventos" });

test("Enter on text writes q; clear button removes it", async () => {
  const { router } = renderApp("/");
  await userEvent.type(await box(), "lesão Pedro{Enter}");
  await waitFor(() => expect(router.state.location.search).toMatchObject({ q: "lesão Pedro" }));
  await userEvent.click(screen.getByRole("button", { name: "Limpar busca" }));
  await waitFor(() => expect(router.state.location.search).not.toHaveProperty("q"));
});

test("arrow to an entity and Enter adds entity=, chip, backspace removes", async () => {
  const { router } = renderApp("/");
  const input = await box();
  await userEvent.type(input, "Fla");
  expect(await screen.findByRole("option", { name: "Flamengo" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Buscar “Fla”" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  expect(screen.getByText("Times")).toBeInTheDocument();
  await userEvent.keyboard("{ArrowDown}{Enter}");
  await waitFor(() => expect(router.state.location.href).toContain(`entity=${FLA}`));
  expect(await screen.findByText("Flamengo")).toBeInTheDocument();
  await userEvent.clear(input);
  await userEvent.keyboard("{Backspace}");
  await waitFor(() => expect(router.state.location.href).not.toContain("entity="));
});

test("Esc closes suggestions, '/' focuses the field, unknown chip label", async () => {
  renderApp(`/?entity=${LIB}`);
  expect(await screen.findByText("Entidade removida")).toBeInTheDocument();
  const input = await box();
  await userEvent.click(document.body);
  await userEvent.keyboard("/");
  expect(input).toHaveFocus();
  await userEvent.type(input, "Fla");
  await screen.findByRole("option", { name: "Flamengo" });
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("listbox", { name: "Sugestões" })).not.toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(input).not.toHaveFocus();
});
