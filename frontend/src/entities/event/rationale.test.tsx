import { render, screen } from "@testing-library/react";

import { RelevanceRationale } from "./rationale";

test("importance rationale is built from codes in the interface language", () => {
  render(
    <RelevanceRationale text="rules: rule:Травма(+6), competition:Чемпионат мира(+2), top_club:(+1), rumor:(-1) · stale" />,
  );
  const list = screen.getByRole("list", { name: "Sinais encontrados" });
  expect(list).toHaveTextContent("Травма+6");
  expect(list).toHaveTextContent("Torneio: Чемпионат мира+2");
  expect(list).toHaveTextContent("Clube de ponta+1");
  expect(list).toHaveTextContent("Marcadores de rumor−1");
  expect(list).toHaveTextContent("Total de pontos8");
  expect(screen.getByText("Nível reduzido: parece notícia antiga.")).toBeInTheDocument();
});

test("no signals and off-topic are sentences, not codes", () => {
  const { rerender } = render(<RelevanceRationale text="rules: no_signals" />);
  expect(screen.getByText(/Nenhum sinal de importância/)).toBeInTheDocument();
  rerender(<RelevanceRationale text="rules: not_sports" />);
  expect(screen.getByText(/Não é sobre esporte/)).toBeInTheDocument();
});
