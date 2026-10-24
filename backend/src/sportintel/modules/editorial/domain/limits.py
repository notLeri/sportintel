"""Лимиты Telegram (BE-T3.7): подпись к фото 1024, сообщение 4096 символов видимого текста."""

import html
import re

_TAG = re.compile(r"<[^>]+>")
_CITE = re.compile(r"\s?\[\d{1,2}\]")


def strip_citations(text: str) -> str:
    return _CITE.sub("", text)


def plain_length(tg_html: str) -> int:
    """Длина без тегов и маркеров [n]; сущности (&amp;) считаются одним символом."""
    return len(html.unescape(strip_citations(_TAG.sub("", tg_html))))


def max_length(has_image: bool) -> int:
    return 1024 if has_image else 4096
