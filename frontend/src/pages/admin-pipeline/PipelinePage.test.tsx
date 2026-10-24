import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const A = "0192f6a1-0000-7000-8000-0000000000f1";

test("stalled queue highlighted; select and retry; retry by code reports remainder", async () => {
  mockMe(makeMe("admin"));
  const retries: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/pipeline/summary"), () =>
      HttpResponse.json({
        articles_24h: { discovered: 1, extracted: 2, enriched: 3, clustered: 4, failed: 5 },
        failures_by_code: [{ code: "fetch_timeout", count: 5 }],
        queues: [
          { queue: "fetch", todo: 9, doing: 1, failed_24h: 0, oldest_todo_age_s: 1200 },
          { queue: "ai", todo: 0, doing: 0, failed_24h: 0, oldest_todo_age_s: null },
        ],
        drafts_failed_24h: 0,
        ingest_lag_p95_s: 600,
      }),
    ),
    http.get(apiUrl("/api/v1/pipeline/failures"), () =>
      HttpResponse.json({
        articles: [
          {
            id: A,
            title: "Falhou",
            url: "https://x/1",
            source_name: "ge",
            failure_code: "fetch_timeout",
            failure_detail: "timeout",
            state_changed_at: "2026-10-09T10:00:00Z",
          },
        ],
        jobs: [],
        next_cursor: null,
      }),
    ),
    http.post(apiUrl("/api/v1/pipeline/failures:retry"), async ({ request }) => {
      const b = await request.json();
      retries.push(b);
      return HttpResponse.json(
        retries.length === 1 ? { retried: 1, remaining: 0 } : { retried: 500, remaining: 20 },
      );
    }),
  );
  renderApp("/admin/pipeline");
  const queues = await screen.findByRole("table", { name: "Filas" });
  const fetchRow = within(queues).getByText("Download de artigos").closest("tr") as HTMLElement;
  expect(fetchRow).toHaveAttribute("data-stalled", "true");
  expect(fetchRow).toHaveTextContent("parada");
  await userEvent.click(await screen.findByRole("checkbox", { name: "Selecionar Falhou" }));
  await userEvent.click(screen.getByRole("button", { name: "Reprocessar selecionados" }));
  await waitFor(() => expect(retries).toEqual([{ article_ids: [A] }]));
  await userEvent.selectOptions(screen.getByLabelText(/Código/), "fetch_timeout");
  await userEvent.click(screen.getByRole("button", { name: "Reprocessar todos com este código" }));
  expect(await screen.findByText("Reprocessados 500, restam 20")).toBeInTheDocument();
});
