import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { DisclaimerBlock } from "./DisclaimerBlock";
import { DraftEditor } from "./DraftEditor";

// ProseMirror в jsdom: нужны прямоугольники выделения.
beforeAll(() => {
  Range.prototype.getClientRects = () =>
    ({
      length: 0,
      item: () => null,
      [Symbol.iterator]: [][Symbol.iterator],
    }) as unknown as DOMRectList;
  Range.prototype.getBoundingClientRect = () => new DOMRect();
  document.elementFromPoint = () => null;
});

test("Ctrl+B produces <b> and toolbar reflects state", async () => {
  const onChange = vi.fn();
  render(<DraftEditor value="texto" onChange={onChange} />);
  const box = await screen.findByRole("textbox", { name: "Editor do rascunho" });
  await userEvent.click(box);
  await userEvent.keyboard("{Control>}a{/Control}{Control>}b{/Control}");
  await waitFor(() => expect(onChange).toHaveBeenLastCalledWith("<b>texto</b>"));
  expect(screen.getByRole("button", { name: "Negrito" })).toHaveAttribute("aria-pressed", "true");
});

test("citation click and unverified highlight that clears after editing", async () => {
  const onCite = vi.fn();
  const { container, rerender } = render(
    <DraftEditor
      value="Pedro marcou dois gols [2]"
      onChange={() => undefined}
      onCitationClick={onCite}
      unverified={[{ text: "Pedro marcou dois gols", title: "Não verificado: dois" }]}
    />,
  );
  const cite = await waitFor(() => {
    const el = container.querySelector(".citation");
    if (!el) throw new Error("no citation");
    return el;
  });
  await userEvent.click(cite);
  expect(onCite).toHaveBeenCalledWith(2);
  expect(container.querySelector(".unverified")).toHaveAttribute("title", "Não verificado: dois");
  rerender(
    <DraftEditor value="Pedro marcou dois gols [2]" onChange={() => undefined} unverified={[]} />,
  );
});

test("disclaimer is an editor-only note without a remove action", () => {
  render(<DisclaimerBlock text="⚠️ Aviso" />);
  expect(screen.getByRole("note")).toHaveTextContent("⚠️ Aviso");
  expect(screen.queryByRole("button", { name: "Remover aviso" })).not.toBeInTheDocument();
});
