import { sanitize } from "@/shared/lib/telegram";

import { docToTg } from "./docToTg";
import { tgToDoc } from "./tgToDoc";

const CASES = [
  "Texto simples",
  "<b>Negrito</b>",
  "<i>Itálico</i> e <u>sublinhado</u>",
  "<s>riscado</s> <code>x = 1</code>",
  '<a href="https://ge.globo.com/x">ge</a>',
  '<a href="https://a.b">https://a.b</a>',
  "<b>forte <i>e itálico</i></b>",
  '<a href="https://x.y"><b>link forte</b></a>',
  "<tg-spoiler>segredo</tg-spoiler>",
  "A &amp; B &lt; C",
  "⚽ Gol do Flamengo!",
  "Привет, мир",
  "linha 1\nlinha 2",
  "parágrafo 1\n\nparágrafo 2",
  "<b>⚽ Título</b>\n\nCorpo com <b>Pedro</b> [1]\n\n#Flamengo #Libertadores",
  "<pre>código\n  indentado</pre>",
  "<blockquote>citação</blockquote>",
  "antes\n\n<blockquote>citação</blockquote>\n\ndepois",
  "<b>a</b><i>b</i>",
  "<u><s>ambos</s></u>",
];

test.each(CASES)("round-trip %s", (x) => {
  expect(docToTg(tgToDoc(x))).toBe(sanitize(x));
});

test("paste strips foreign markup", () => {
  expect(docToTg(tgToDoc("<div>ok<script>alert(1)</script></div><p>x</p>"))).toBe("okx");
});

test("empty and single line", () => {
  expect(docToTg(tgToDoc(""))).toBe("");
  expect(tgToDoc("uma linha").content).toHaveLength(1);
});
