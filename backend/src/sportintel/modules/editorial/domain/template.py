"""TemplateDrafter — шаблонный черновик без LM (ADR-004, BE-T3.9)."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sportintel.modules.editorial.domain.draft_output import (
    HEADLINE_MAX,
    PARAGRAPH_MAX,
    DraftOutput,
)

PROMPT_VERSION = "template/v1"
ALSO_REPORTED = {
    "pt-BR": "Também noticiado por: {names}.",
    "en": "Also reported by: {names}.",
    "ru": "Также сообщают: {names}.",
}
_SENT = re.compile(r"(?<=[.!?…])\s+")


@dataclass(frozen=True)
class TemplateResult:
    output: DraftOutput
    main_article_id: Any
    source_link: tuple[str, str] | None
    language: str  # язык текста поста (язык основной статьи)


def cut_words(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    head = text[: limit - 1]
    if text[limit - 1] != " ":  # не рвать слово
        head = head.rsplit(" ", 1)[0]
    return head.rstrip(",;:") + "…"


def cut_sentences(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    out = ""
    for s in _SENT.split(text):
        if len(out) + len(s) + 1 > limit:
            break
        out = f"{out} {s}".strip()
    return out or cut_words(text, limit)


def hashtag(name: str) -> str:
    """«Vasco da Gama» → #VascoDaGama; символы вне формата удаляются."""
    words = re.findall(r"[0-9A-Za-zÀ-ÿ]+", unicodedata.normalize("NFC", name))
    return "#" + "".join(w[:1].upper() + w[1:] for w in words)[:30]


def competition_for(pack: Any, lang: str) -> list[str]:
    """Турнир — на языке поста («World Cup», а не «Copa do Mundo»); нет перевода — как есть."""
    if not pack.competition_name:
        return []
    names = getattr(pack, "competition_name_i18n", None) or {}
    return [names.get(lang) or pack.competition_name]


def content_language(code: str | None, fallback: str) -> str:
    """Язык текста по коду статьи: «pt», «pt-PT» → pt-BR, «ru-RU» → ru, «es» → es.
    fallback — только если язык статьи неизвестен совсем."""
    base = (code or "").split("-")[0].lower()
    return {"pt": "pt-BR"}.get(base, base) or fallback


def build(pack: Any, settings: Any, language: str = "en") -> TemplateResult | None:
    """None — нет основных статей (ручное событие без источников).
    Текст шаблона — лид основной статьи без перевода: язык поста = язык этой статьи."""
    if not pack.sources:
        return None
    main = pack.sources[0]
    language = content_language(getattr(main, "language", None), language)
    lead = cut_sentences(main.lead or main.title, PARAGRAPH_MAX - 4)
    paragraphs = [f"{lead} [1]"]
    others = list(
        dict.fromkeys(
            s.source_name
            for s in pack.sources[1:]
            if s.source_name and s.source_name != main.source_name
        )
    )
    if settings.template_also_reported and others:
        paragraphs.append(
            ALSO_REPORTED.get(language, ALSO_REPORTED["en"]).format(names=", ".join(others))
        )
    bold = [n for n in pack.known_names if n and n in paragraphs[0]][:3]
    tags = [hashtag(n) for n in [*competition_for(pack, language), *pack.team_names]]
    out = DraftOutput(
        emoji=settings.emojis.get(pack.sport_id) if pack.sport_id else None,
        headline=cut_words(pack.title, HEADLINE_MAX),
        paragraphs=paragraphs,
        bold_phrases=bold,
        hashtags=tags,
    )
    link = (main.source_name, main.url) if settings.include_source_link and main.url else None
    return TemplateResult(out, main.article_id, link, language)
