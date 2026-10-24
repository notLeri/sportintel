import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { render } from "@testing-library/react";

import { Toaster } from "@/shared/ui";

import { server } from "../../../tests/setup/msw/server";
import { apiUrl } from "../../../tests/setup/render";
import { CopyButton } from "./CopyButton";

const SRC = {
  draftId: "0192f6a1-0000-7000-8000-0000000000d1",
  versionN: 2,
  tgHtml: "<b>Gol</b> [1]",
};

function setup(clipboard: Partial<Clipboard>) {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: clipboard });
  const copied: unknown[] = [];
  server.use(
    http.post(apiUrl(`/api/v1/drafts/${SRC.draftId}:copied`), async ({ request }) => {
      copied.push(await request.json());
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(
    <>
      <CopyButton source={SRC} />
      <Toaster />
    </>,
  );
  return copied;
}

afterEach(() => {
  // @ts-expect-error — сброс заглушки
  delete globalThis.ClipboardItem;
});

test("writes html and plain without citations and records the copy", async () => {
  const items: Record<string, Blob>[] = [];
  globalThis.ClipboardItem = class {
    constructor(public data: Record<string, Blob>) {
      items.push(data);
    }
  } as unknown as typeof ClipboardItem;
  const copied = setup({ write: vi.fn().mockResolvedValue(undefined) });
  await userEvent.click(screen.getByRole("button", { name: "Copiar" }));
  await waitFor(() => expect(copied).toEqual([{ version_n: 2 }]));
  const [item] = items;
  expect(await item?.["text/html"]?.text()).toBe("<b>Gol</b>");
  expect(await item?.["text/plain"]?.text()).toBe("Gol");
  expect(await screen.findByText("Post copiado")).toBeInTheDocument();
});

test("falls back to writeText, then to a manual dialog", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  setup({ writeText });
  await userEvent.click(screen.getByRole("button", { name: "Copiar" }));
  await waitFor(() => expect(writeText).toHaveBeenCalledWith("Gol"));
});

test("browser refusal opens the manual copy dialog", async () => {
  setup({ writeText: vi.fn().mockRejectedValue(new Error("denied")) });
  await userEvent.click(screen.getByRole("button", { name: "Copiar" }));
  expect(
    await screen.findByRole("dialog", { name: "Copie manualmente (Ctrl+C)" }),
  ).toBeInTheDocument();
  expect(screen.getByRole("textbox")).toHaveValue("Gol");
});
