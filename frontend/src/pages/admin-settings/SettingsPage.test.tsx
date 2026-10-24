import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import settings from "../../../tests/fixtures/settings.json";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

function serve(onPut: (key: string, body: unknown) => Response) {
  server.use(
    http.get(apiUrl("/api/v1/settings"), () => HttpResponse.json({ items: settings })),
    http.put(apiUrl("/api/v1/settings/:key"), async ({ params, request }) =>
      onPut(String(params.key), await request.json()),
    ),
  );
}

test("clustering numbers: edit and save; server error shown", async () => {
  mockMe(makeMe("admin"));
  const puts: unknown[] = [];
  serve((key, body) => {
    puts.push({ key, body });
    return puts.length === 1
      ? HttpResponse.json(
          {
            code: "settings.invalid_value",
            title: "Invalid",
            status: 422,
            errors: [{ field: "t_low", code: "x", message: "t_low < t_high" }],
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        )
      : HttpResponse.json(settings[0]);
  });
  renderApp("/admin/settings");
  const form = await screen.findByRole("form", { name: "clustering" });
  const tHigh = within(form).getByLabelText("Limiar “mesmo evento”");
  expect(tHigh).toHaveValue(0.58);
  await userEvent.clear(tHigh);
  await userEvent.type(tHigh, "0.6");
  await userEvent.click(within(form).getByRole("button", { name: "Salvar" }));
  expect(await within(form).findByRole("alert")).toHaveTextContent("t_low < t_high");
  await userEvent.click(within(form).getByRole("button", { name: "Salvar" }));
  await waitFor(() => expect(puts).toHaveLength(2));
  expect((puts[0] as { body: { value: { t_high: number } } }).body.value.t_high).toBe(0.6);
});

test("drafts channel_examples as a list and ai_routing selects; LM fields disabled without a model", async () => {
  mockMe(
    makeMe("admin", {
      system_status: {
        ai: { mode: "rules", llm: { configured: false, available: false, model: null } },
        sources_down: 0,
        pipeline_delayed: false,
      },
    }),
  );
  serve(() => HttpResponse.json(settings[1]));
  renderApp("/admin/settings");
  await userEvent.click(await screen.findByRole("button", { name: "Rascunhos e feed" }));
  expect(
    within(await screen.findByRole("form", { name: "drafts" })).getByLabelText("Exemplos de posts"),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Regras ou LM por etapa" }));
  const form = await screen.findByRole("form", { name: "ai_routing" });
  expect(within(form).getByLabelText("Marcação de artigos")).toHaveValue("rules");
  expect(within(form).getByLabelText("Modelo de IA")).toBeDisabled();
  expect(within(form).getByRole("status")).toHaveTextContent("Modelo local não configurado");
});

test("enrich_rules list of objects is editable", async () => {
  mockMe(makeMe("admin"));
  serve(() => HttpResponse.json(settings[3]));
  renderApp("/admin/settings");
  await userEvent.click(await screen.findByRole("button", { name: "Regras de enriquecimento" }));
  const form = await screen.findByRole("form", { name: "enrich_rules" });
  expect(within(form).getAllByLabelText("Peso").length).toBeGreaterThan(5);
});
