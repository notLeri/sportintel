import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl, makeMe, mockMe, renderApp } from "../../../tests/setup/render";

const U = {
  id: "0192f6a1-0000-7000-8000-0000000000c1",
  email: "ana@corp.com",
  display_name: "Ana",
  role: "admin",
  active: true,
  invited: false,
  last_login_at: "2026-10-09T10:00:00Z",
  created_at: "2026-10-01T10:00:00Z",
  version: 1,
  has_password: false,
};

beforeEach(() => {
  mockMe(makeMe("admin"));
  vi.spyOn(window, "confirm").mockReturnValue(true);
});
afterEach(() => vi.restoreAllMocks());

test("invite a user and handle duplicates", async () => {
  const posts: unknown[] = [];
  server.use(
    http.get(apiUrl("/api/v1/users"), () => HttpResponse.json({ items: [U] })),
    http.post(apiUrl("/api/v1/users"), async ({ request }) => {
      posts.push(await request.json());
      return posts.length === 1
        ? HttpResponse.json(
            {
              ...U,
              id: "0192f6a1-0000-7000-8000-0000000000c2",
              email: "novo@corp.com",
              invited: true,
            },
            { status: 201 },
          )
        : HttpResponse.json(
            { code: "user.email_exists", title: "x", status: 409 },
            { status: 409, headers: { "Content-Type": "application/problem+json" } },
          );
    }),
  );
  renderApp("/admin/users");
  await userEvent.click(await screen.findByRole("button", { name: "Convidar usuário" }));
  let dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("E-mail"), "novo@corp.com");
  await userEvent.selectOptions(within(dialog).getByLabelText("Papel"), "editor");
  await userEvent.click(within(dialog).getByRole("button", { name: "Convidar" }));
  await waitFor(() =>
    expect(posts).toEqual([
      { email: "novo@corp.com", role: "editor", display_name: null, password: null },
    ]),
  );
  await userEvent.click(screen.getByRole("button", { name: "Convidar usuário" }));
  dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("E-mail"), "ana@corp.com");
  await userEvent.click(within(dialog).getByRole("button", { name: "Convidar" }));
  expect(await within(dialog).findByRole("alert")).toHaveTextContent("Já existe");
});

test("role change with confirmation; last admin message", async () => {
  server.use(
    http.get(apiUrl("/api/v1/users"), () => HttpResponse.json({ items: [U] })),
    http.patch(apiUrl(`/api/v1/users/${U.id}`), () =>
      HttpResponse.json(
        { code: "user.last_admin", title: "x", status: 409 },
        { status: 409, headers: { "Content-Type": "application/problem+json" } },
      ),
    ),
  );
  renderApp("/admin/users");
  await userEvent.selectOptions(await screen.findByLabelText("Papel de Ana"), "editor");
  expect(window.confirm).toHaveBeenCalled();
  expect(
    await screen.findByText("É necessário pelo menos um administrador ativo"),
  ).toBeInTheDocument();
});
