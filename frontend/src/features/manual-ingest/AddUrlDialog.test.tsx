import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { server } from "../../../tests/setup/msw/server";
import { normalizeUrlInput } from "./useAddUrl";

test.each([
  ["ge.globo.com/x", "https://ge.globo.com/x"],
  ["  http://a.com  ", "http://a.com/"],
  ["ftp://a.com", null],
  ["", null],
])("normalizeUrlInput(%j)", (raw, expected) => {
  expect(normalizeUrlInput(raw)).toBe(expected);
});

async function openDialog() {
  mockMe(makeMe("researcher"));
  renderApp("/articles");
  await userEvent.click(await screen.findByRole("button", { name: "Adicionar link" }));
  return screen.getByLabelText("URL");
}

test("empty input disables submit; invalid URL shows error", async () => {
  const input = await openDialog();
  expect(screen.getByRole("button", { name: "Adicionar" })).toBeDisabled();
  await userEvent.type(input, "ftp://x.com/a");
  await userEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Informe um link http(s) válido.");
});

test("network error keeps dialog; retry reuses the same Idempotency-Key", async () => {
  const keys: (string | null)[] = [];
  let fail = true;
  server.use(
    http.post(apiUrl("/api/v1/articles"), async ({ request }) => {
      keys.push(request.headers.get("idempotency-key"));
      expect(await request.json()).toEqual({ url: "https://ge.globo.com/x" });
      if (fail) {
        fail = false;
        return HttpResponse.error();
      }
      return HttpResponse.json(
        { article_id: "0192f6a1-0000-7000-8000-000000000001", created: true, state: "discovered" },
        { status: 202 },
      );
    }),
  );
  const input = await openDialog();
  await userEvent.type(input, "ge.globo.com/x");
  await userEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sem conexão");
  expect(screen.getByLabelText("URL")).toHaveValue("ge.globo.com/x");
  await userEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  await waitFor(() => expect(keys).toHaveLength(2));
  expect(keys[0]).toBe(keys[1]);
  expect(await screen.findByText("Link adicionado. Processando…")).toBeInTheDocument();
});

test("existing link shows a toast", async () => {
  server.use(
    http.post(apiUrl("/api/v1/articles"), () =>
      HttpResponse.json(
        { article_id: "0192f6a1-0000-7000-8000-000000000001", created: false, state: "extracted" },
        { status: 202 },
      ),
    ),
  );
  const input = await openDialog();
  await userEvent.type(input, "https://ge.globo.com/x");
  await userEvent.click(screen.getByRole("button", { name: "Adicionar" }));
  expect(await screen.findByText("Este link já existe")).toBeInTheDocument();
});
