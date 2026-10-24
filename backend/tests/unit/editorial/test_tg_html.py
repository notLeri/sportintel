import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from sportintel.modules.editorial.domain.tg_html import sanitize_tg_html as s

XSS = [
    "<script>alert(1)</script>",
    "<img src=x onerror=alert(1)>",
    "<svg/onload=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    '<a href="JaVaScRiPt:alert(1)">x</a>',
    '<a href="data:text/html;base64,PHNjcmlwdD4=">x</a>',
    "<iframe src=https://evil.example></iframe>",
    '<b onclick="alert(1)">x</b>',
    "<body onload=alert(1)>",
    "<style>*{}</style>",
    '<a href="https://ok.example" onmouseover="alert(1)">x</a>',
    "<object data=x></object>",
    "<embed src=x>",
    "<math><mi xlink:href=javascript:alert(1)>x</mi></math>",
    '<div style="background:url(javascript:alert(1))">x</div>',
    "<!--<script>-->x",
    "<input autofocus onfocus=alert(1)>",
]


@pytest.mark.parametrize("payload", XSS)
def test_xss_removed(payload: str) -> None:
    out = s(payload)
    low = out.lower()
    for bad in (
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
    ):
        assert bad not in low, (payload, out)


def test_paragraphs_breaks_and_spoiler() -> None:
    assert s("<p>Um</p><p>Dois<br>três</p>") == "Um\n\nDois\ntrês"
    assert s('<span class="tg-spoiler">segredo</span>') == "<tg-spoiler>segredo</tg-spoiler>"
    assert s("a\n\n\n\n\nb") == "a\n\nb"
    assert s('<a href="https://ge.globo.com/x">ge</a>') == '<a href="https://ge.globo.com/x">ge</a>'
    assert s("<a>sem link</a>") == "sem link"


def test_text_escaping_emoji_cyrillic() -> None:
    assert s("Flamengo & Vasco < 2 ⚽ Привет") == "Flamengo &amp; Vasco &lt; 2 ⚽ Привет"


TOKENS = [
    *list("ab <>/&\"'=\n"),
    "<b>",
    "</b>",
    "<p>",
    "</p>",
    "<br>",
    '<a href="https://x.y">',
    "</a>",
    "<i>",
    "[1]",
]


@settings(max_examples=200, deadline=None)
@given(st.lists(st.sampled_from(TOKENS), max_size=30).map("".join))
def test_idempotent(raw: str) -> None:
    once = s(raw)
    assert s(once) == once
