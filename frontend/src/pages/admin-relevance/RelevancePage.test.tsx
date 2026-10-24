import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const RULES = {
  relevance_rules: [
    { name: "Травма", weight: 3, words: { "pt-BR": ["lesão", "desfalque"], en: ["injury"] } },
  ],
  competition_weight: {},
  level_thresholds: { HIGH: 6, MEDIUM: 3, LOW: 1 },
  body_weight: 0.5,
  top_team_bonus: 1,
  rumor_penalty: 1,
  clickbait_penalty: 2,
  rumor_markers: { "pt-BR": ["estaria"] },
  sport_keywords: { football: ["gol"] },
  version: 5,
};

test("admin opens on Pipeline by default", async () => {
  mockMe(makeMe("admin"));
  server.use(
    http.get(apiUrl("/api/v1/pipeline/summary"), () =>
      HttpResponse.json({
        articles_24h: {},
        failures_by_code: [],
        queues: [],
        drafts_failed_24h: 0,
        ingest_lag_p95_s: null,
      }),
    ),
  );
  const { router } = renderApp("/admin");
  await waitFor(() => expect(router.state.location.pathname).toBe("/admin/pipeline"));
  expect(screen.getByRole("link", { name: "Pipeline" })).toHaveAttribute("data-status", "active");
});

test("formula in words, unsaved rules checked on a headline, save keeps other fields", async () => {
  mockMe(makeMe("admin"));
  const checks: { rules: typeof RULES }[] = [];
  const puts: { value: typeof RULES }[] = [];
  server.use(
    http.get(apiUrl("/api/v1/settings/enrich_rules"), () =>
      HttpResponse.json({ key: "enrich_rules", value: RULES }),
    ),
    http.post(apiUrl("/api/v1/relevance*"), async ({ request }) => {
      const body = (await request.json()) as { rules: typeof RULES };
      checks.push(body);
      const high = body.rules.level_thresholds.HIGH;
      return HttpResponse.json({
        is_sports: true,
        sport: "football",
        score: 8,
        level: 8 >= high ? "HIGH" : "MEDIUM",
        parts: [
          { kind: "rule", name: "Травма", points: 6, where: "title", label: "rule:Травма(+6)" },
          { kind: "competition", name: "Brasileirão", points: 2, where: "entity", label: "x" },
        ],
      });
    }),
    http.put(apiUrl("/api/v1/settings/enrich_rules"), async ({ request }) => {
      puts.push((await request.json()) as { value: typeof RULES });
      return HttpResponse.json({ key: "enrich_rules", value: RULES });
    }),
  );
  renderApp("/admin/relevance");
  const how = await screen.findByRole("region", { name: "Como a importância é calculada" });
  expect(how).toHaveTextContent("peso × 0.5");
  expect(how).toHaveTextContent("a partir de 6 — «Alta», a partir de 3 — «Média»");

  await userEvent.type(screen.getByLabelText("Título"), "Flamengo tem lesão");
  await userEvent.click(screen.getByRole("button", { name: "Testar" }));
  const result = await screen.findByRole("region", { name: "Resultado do teste" });
  expect(result).toHaveTextContent("Pontos: 8");
  expect(within(result).getByRole("list")).toHaveTextContent("“Травма” — no título+6");
  expect(result).toHaveTextContent("Torneio: Brasileirão+2");

  // порог «Высокой» поднят — проверка пересчитывается сама по несохранённым правилам
  const high = screen.getByRole("spinbutton", { name: /«Alta» — a partir de pontos/ });
  await userEvent.clear(high);
  await userEvent.type(high, "10");
  await waitFor(() => expect(checks.at(-1)?.rules.level_thresholds.HIGH).toBe(10));
  expect(await within(result).findByText("Relevância média")).toBeInTheDocument();
  expect(puts).toHaveLength(0);

  // слова — по языкам источников; запятая не пропадает, разбор — при уходе из поля
  const ru = screen.getByRole("textbox", { name: "Травма: Palavras em fontes em russo" });
  await userEvent.type(ru, "травма, травмы");
  await userEvent.tab();
  await userEvent.click(screen.getByRole("button", { name: "Salvar regras" }));
  await waitFor(() => expect(puts).toHaveLength(1));
  expect(puts[0]?.value).toMatchObject({
    level_thresholds: { HIGH: 10, MEDIUM: 3, LOW: 1 },
    sport_keywords: { football: ["gol"] }, // остальное — как было
    relevance_rules: [
      {
        name: "Травма",
        weight: 3,
        words: { "pt-BR": ["lesão", "desfalque"], en: ["injury"], ru: ["травма", "травмы"] },
      },
    ],
    version: 6,
  });
});
