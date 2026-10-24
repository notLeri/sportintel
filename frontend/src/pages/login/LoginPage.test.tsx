import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";
import { server } from "../../../tests/setup/msw/server";

beforeEach(() => mockMe(null));

test("shows error from query", async () => {
  renderApp("/login?error=auth.not_allowed");
  expect(await screen.findByRole("alert")).toHaveTextContent("Seu e-mail não tem acesso");
});

test("unknown error code falls back to a generic message", async () => {
  renderApp("/login?error=whatever");
  expect(await screen.findByRole("alert")).toHaveTextContent("Não foi possível entrar");
});

test("Google button is a plain link keeping a safe next", async () => {
  renderApp("/login?next=%2Fevents%2F1");
  const link = await screen.findByRole("link", { name: "Entrar com Google" });
  expect(link).toHaveAttribute("href", "/auth/login?next=%2Fevents%2F1");
});

test("open redirect in next is dropped", async () => {
  renderApp("/login?next=%2F%2Fevil.com");
  const link = await screen.findByRole("link", { name: "Entrar com Google" });
  expect(link).toHaveAttribute("href", "/auth/login?next=%2F");
});

test("dev login signs in and goes to next", async () => {
  server.use(
    http.post(apiUrl("/auth/dev-login"), async ({ request }) => {
      const body = (await request.json()) as {
        email: string;
        role: "researcher" | "editor" | "admin";
      };
      mockMe(makeMe(body.role, { email: body.email }));
      return HttpResponse.json(makeMe(body.role, { email: body.email }));
    }),
  );
  const { router } = renderApp("/login?next=%2Farticles");
  const form = await screen.findByRole("form", { name: /Login de desenvolvimento/ });
  await userEvent.selectOptions(screen.getByLabelText("Papel"), "researcher");
  await userEvent.click(screen.getByRole("button", { name: /^Entrar como / }));
  await vi.waitFor(() => expect(router.state.location.pathname).toBe("/articles"));
  expect(form).not.toBeInTheDocument();
});

test("password login signs in and goes to next", async () => {
  server.use(
    http.post(apiUrl("/auth/password-login"), async ({ request }) => {
      const body = (await request.json()) as { email: string; password: string };
      if (body.password !== "long-password") {
        return HttpResponse.json(
          { code: "auth.bad_credentials", title: "x", status: 401 },
          { status: 401, headers: { "Content-Type": "application/problem+json" } },
        );
      }
      mockMe(makeMe("editor", { email: body.email }));
      return HttpResponse.json(makeMe("editor", { email: body.email }));
    }),
  );
  const { router } = renderApp("/login?next=%2Ffeed");
  await userEvent.type(
    await screen.findByLabelText("E-mail", { selector: "#login-email" }),
    "a@b.co",
  );
  await userEvent.type(screen.getByLabelText("Senha"), "wrong-password");
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("E-mail ou senha incorretos");
  await userEvent.clear(screen.getByLabelText("Senha"));
  await userEvent.type(screen.getByLabelText("Senha"), "long-password");
  await userEvent.click(screen.getByRole("button", { name: "Entrar" }));
  await vi.waitFor(() => expect(router.state.location.pathname).toBe("/feed"));
});

test("Google button is hidden when the server has OIDC off", async () => {
  const meta = document.createElement("meta");
  meta.name = "app-oidc";
  meta.content = "off";
  document.head.append(meta);
  try {
    renderApp("/login");
    expect(await screen.findByLabelText("Senha")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Entrar com Google" })).not.toBeInTheDocument();
  } finally {
    meta.remove();
  }
});
