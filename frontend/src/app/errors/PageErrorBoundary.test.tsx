import { render, screen } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";

import { AppError } from "@/shared/api";
import { createI18n } from "@/shared/i18n";

import { PageErrorBoundary } from "./PageErrorBoundary";

function Boom({ error }: { error: unknown }): never {
  throw error;
}

function renderBoundary(error: unknown) {
  vi.spyOn(console, "error").mockImplementation(() => {});
  render(
    <I18nextProvider i18n={createI18n("pt-BR")}>
      <PageErrorBoundary>
        <Boom error={error} />
      </PageErrorBoundary>
    </I18nextProvider>,
  );
}

test("catches child render error and offers reload", () => {
  renderBoundary(new Error("kaboom"));
  expect(screen.getByRole("alert")).toHaveTextContent("Algo deu errado");
  expect(screen.getByRole("button", { name: "Recarregar" })).toBeInTheDocument();
});

test("shows request_id for AppError", () => {
  renderBoundary(
    new AppError({ status: 500, code: "common.internal", title: "x", requestId: "req-1" }),
  );
  expect(screen.getByText("ID da requisição: req-1")).toBeInTheDocument();
});

test("chunk load error suggests reload of new version", () => {
  renderBoundary(new TypeError("Failed to fetch dynamically imported module: /assets/x.js"));
  expect(screen.getByText(/nova versão/)).toBeInTheDocument();
});
