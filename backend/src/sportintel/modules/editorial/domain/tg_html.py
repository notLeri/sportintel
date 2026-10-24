"""Санитизация тела черновика под подмножество Telegram HTML (BE-T3.8)."""

import re

import nh3

ALLOWED_TAGS = {
    "b",
    "strong",
    "i",
    "em",
    "u",
    "ins",
    "s",
    "strike",
    "del",
    "a",
    "code",
    "pre",
    "blockquote",
    "tg-spoiler",
}
ALLOWED_ATTRS = {"a": {"href"}}

_BR = re.compile(r"<br\s*/?>", re.IGNORECASE)
_P_BREAK = re.compile(r"</p>\s*<p[^>]*>", re.IGNORECASE)
_P = re.compile(r"</?p[^>]*>", re.IGNORECASE)
_SPOILER = re.compile(r'<span\s+class="tg-spoiler"\s*>(.*?)</span>', re.IGNORECASE | re.DOTALL)
_A_NO_HREF = re.compile(r"<a>(.*?)</a>", re.DOTALL)
_MANY_NL = re.compile(r"\n{3,}")


def sanitize_tg_html(raw: str) -> str:
    html = raw.replace("\r\n", "\n")
    html = _BR.sub("\n", html)
    html = _P_BREAK.sub("\n\n", html)
    html = _P.sub("", html)
    html = _SPOILER.sub(r"<tg-spoiler>\1</tg-spoiler>", html)
    html = nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        url_schemes={"http", "https"},
        link_rel=None,
        strip_comments=True,
    )
    html = _A_NO_HREF.sub(r"\1", html)  # <a> без href (например, javascript:) — остаётся текст
    return _MANY_NL.sub("\n\n", html).strip()
