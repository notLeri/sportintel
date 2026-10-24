import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { eventItem } from "../../../tests/fixtures/events";
import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { parseUrlLines } from "./useCreateEvent";

beforeEach(() => mockMe(makeMe("researcher")));

test("parses URL lines", () => {
  expect(parseUrlLines("ge.globo.com/a\n\n https://x.y/b \nnot a url")).toEqual([
    "https://ge.globo.com/a",
    "https://x.y/b",
    null,
  ]);
});

test("creates an event, reuses the key on retry, selects it; server URL error marks the line", async () => {
  const keys: string[] = [];
  const created = { ...eventItem(7), skipped_urls: [] };
  server.use(
    http.post(apiUrl("/api/v1/events"), async ({ request }) => {
      keys.push(request.headers.get("Idempotency-Key") ?? "");
      const body = (await request.json()) as { urls: string[] };
      if (keys.length === 1)
        return HttpResponse.json(
          {
            code: "common.validation_failed",
            title: "x",
            status: 422,
            errors: [{ field: "urls[1]", code: "article.invalid_url", message: "bad" }],
          },
          { status: 422, headers: { "Content-Type": "application/problem+json" } },
        );
      expect(body.urls).toEqual(["https://ge.globo.com/a"]);
      return HttpResponse.json(created, { status: 201 });
    }),
  );
  const { router } = renderApp("/");
  await userEvent.click(await screen.findByRole("button", { name: "Novo evento" }));
  const dialog = await screen.findByRole("dialog", { name: "Novo evento" });
  const submit = within(dialog).getByRole("button", { name: "Criar" });
  expect(submit).toBeDisabled();
  await userEvent.type(within(dialog).getByLabelText("Título"), "Escalação confirmada");
  const links = within(dialog).getByLabelText("Links das fontes");
  await userEvent.type(links, "ge.globo.com/a{Enter}https://x.example/b");
  await userEvent.click(submit);
  expect(await within(dialog).findByText("Link inválido na linha 2.")).toBeInTheDocument();
  await userEvent.clear(links);
  await userEvent.type(links, "ge.globo.com/a");
  await userEvent.click(submit);
  await waitFor(() => expect(router.state.location.search).toMatchObject({ event: created.id }));
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});
