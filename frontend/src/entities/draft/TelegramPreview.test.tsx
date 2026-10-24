import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TelegramPreview } from "./TelegramPreview";

test("renders SRS §9 elements and reveals spoiler from keyboard", async () => {
  render(
    <TelegramPreview
      channelName="Prévia do canal"
      imageUrl="https://img.example/x.jpg"
      tgHtml={
        '<b>⚽ Título</b>\n\nTexto <i>itálico</i> com <b>Pedro</b> [1]\n\n#Flamengo\n\n<a href="https://ge.globo.com/x">ge</a> <tg-spoiler>segredo</tg-spoiler>'
      }
    />,
  );
  const post = screen.getByRole("article", { name: "Prévia do post no Telegram" });
  expect(post.querySelector("b")).toHaveTextContent("⚽ Título");
  expect(post.querySelector("i")).toHaveTextContent("itálico");
  expect(post.querySelector(".tg-hashtag")).toHaveTextContent("#Flamengo");
  expect(screen.getByRole("link", { name: "ge" })).toHaveAttribute("rel", "noopener noreferrer");
  expect(post).not.toHaveTextContent("[1]");
  expect(post.querySelector("img")).toHaveAttribute("loading", "lazy");
  const spoiler = screen.getByRole("button", { name: "Spoiler" });
  spoiler.focus();
  await userEvent.keyboard("{Enter}");
  expect(spoiler).toHaveClass("tg-spoiler--open");
});

test("empty body placeholder", () => {
  render(<TelegramPreview channelName="c" imageUrl={null} tgHtml="  " />);
  expect(screen.getByText("Sem conteúdo")).toBeInTheDocument();
});
