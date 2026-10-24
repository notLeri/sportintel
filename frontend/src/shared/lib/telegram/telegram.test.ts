import cases from "../../../../../fixtures/telegram/length_cases.json";

import { buildClipboard, plainLength, sanitize, stripCitations, toDisplayHtml } from ".";

const XSS = [
  "<script>alert(1)</script>",
  "<img src=x onerror=alert(1)>",
  "<svg/onload=alert(1)>",
  '<a href="javascript:alert(1)">x</a>',
  '<a href="data:text/html;base64,PHN">x</a>',
  "<iframe src=https://evil.example></iframe>",
  '<b onclick="alert(1)">x</b>',
  "<style>*{}</style>",
  '<a href="https://ok.example" onmouseover="alert(1)">x</a>',
  "<object data=x></object>",
  "<input autofocus onfocus=alert(1)>",
  '<div style="background:url(javascript:alert(1))">x</div>',
  '<tg-spoiler onclick="x">s</tg-spoiler>',
];

test.each(XSS)("sanitize removes %s", (payload) => {
  const out = sanitize(payload).toLowerCase();
  for (const bad of [
    "<script",
    "onerror",
    "onload",
    "javascript:",
    "<iframe",
    "onclick",
    "<style",
    "onmouseover",
    "<img",
    "<svg",
    "data:",
    "<input",
    "<div",
  ])
    expect(out).not.toContain(bad);
});

test("plainLength matches the backend fixture", () => {
  for (const c of cases) expect([c.html, plainLength(c.html)]).toEqual([c.html, c.length]);
});

test("citations, hashtags outside links, spoiler, line breaks", () => {
  expect(stripCitations("Texto [1] e [12].")).toBe("Texto e.");
  const html = toDisplayHtml(
    'Gol #Flamengo [1]\n<a href="https://x.y/#Tag">#Link</a> <tg-spoiler>s</tg-spoiler>',
    { withCitations: false },
  );
  expect(html).toContain('<span class="tg-hashtag">#Flamengo</span>');
  expect(html).not.toContain("[1]");
  expect(html).toContain('href="https://x.y/#Tag"');
  expect(html).toContain(">#Link</a>");
  expect(html).toContain(
    '<span class="tg-spoiler" tabindex="0" role="button" aria-label="Spoiler">s</span>',
  );
  expect(html).toContain("<br>");
  expect(toDisplayHtml("A [1]", { withCitations: true })).toContain("[1]");
});

test("buildClipboard html and plain", () => {
  const c = buildClipboard(
    '<b>Título</b> [1]\n<a href="https://ge.globo.com/x">ge</a> <tg-spoiler>s</tg-spoiler> <a href="https://a.b">https://a.b</a>',
  );
  expect(c.html).toBe(
    '<b>Título</b><br><a href="https://ge.globo.com/x">ge</a> s <a href="https://a.b">https://a.b</a>',
  );
  expect(c.plain).toBe("Título\nge (https://ge.globo.com/x) s https://a.b");
});
