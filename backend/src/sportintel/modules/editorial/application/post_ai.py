"""Telegram-пост от ИИ по формату редакции: заголовок и текст по образцу поста.

Модель пишет текст с разметкой **жирный** и [фраза](n) — ссылка на источник n. Код превращает её
в Telegram HTML: адреса берутся только из источников события, не из ответа модели. Эмодзи,
хэштеги и ссылку в конце добавляет код по настройкам формата.
"""

import html
import re
from typing import Any

from pydantic import BaseModel, Field

from sportintel.modules.editorial.domain.draft_output import HASHTAG, MAX_PARAGRAPHS
from sportintel.modules.editorial.domain.template import competition_for, hashtag
from sportintel.platform.llm import LlmProvider

PROMPT_VERSION = "post/v2"
MAX_SOURCES = 5
LEAD_MAX = 600
BODY_MAX = 1200
LANG_NAMES = {"ru": "Russian", "en": "English", "pt-BR": "Brazilian Portuguese"}
_LINK = re.compile(r"\[([^\]\n]+)\]\((\d+)\)")
_BOLD = re.compile(r"\*\*([^*\n]+)\*\*")
_A = re.compile(r'<a\s[^>]*href="([^"]*)"[^>]*>(.*?)</a>', re.S)
_B = re.compile(r"<(b|strong)>(.*?)</\1>", re.S)
_TAG = re.compile(r"<[^>]+>")


class AiPost(BaseModel):
    headline: str = Field(max_length=120, description="Short news headline, no emoji")
    body: str = Field(
        max_length=BODY_MAX,
        description="Post text after the headline; paragraphs separated by a blank line",
    )


SYSTEM = """You are an editor of a sports and iGaming Telegram channel.
Write a post in {lang} about ONE event from the numbered articles (they may be in any language).
- headline: one line, what happened. body: the post text after the headline.
- Use ONLY facts from the articles; never invent names, numbers, dates or quotes.
- Neutral news tone: no clickbait, no emojis, no hashtags.
- Never say whether the news is confirmed or a rumor — the editor sees that separately.
- Mark up to 3 key names as **bold**.
{links}- Write natural {lang}, as a native news editor would.{example}{instructions}"""
LINKS_ON = (
    "- Link sources inside the text: wrap a short phrase as [phrase](n), where n is the article "
    "number, e.g. [reported by ge](1). Only numbers from the list; no raw URLs.\n"
)
LINKS_OFF = "- No links and no source names in the text.\n"
EXAMPLE = """

Example of a finished post about ANOTHER event. Copy its structure, length, tone and the way it
links sources — never its facts. Emoji, hashtags and the trailing source link are added
automatically: do not write them.
---
{0}
---"""


def example_markup(tg_html: str) -> str:
    """Образец из Telegram HTML → разметка модели: ссылки [фраза](n), жирный **…**."""
    refs: dict[str, int] = {}

    def link(m: re.Match[str]) -> str:
        n = refs.setdefault(m.group(1), len(refs) + 1)
        return f"[{_TAG.sub('', m.group(2))}]({n})"

    text = _B.sub(lambda m: f"**{_TAG.sub('', m.group(2))}**", _A.sub(link, tg_html))
    return html.unescape(_TAG.sub("", text)).strip()


def post_prompt(pack: Any, lang: str, cfg: Any) -> tuple[str, str]:
    lines = [f"Event title: {pack.title}", ""]
    for i, s in enumerate(pack.sources[:MAX_SOURCES], 1):
        lines += [f"[{i}] {s.source_name}: {s.title}", (s.lead or "")[:LEAD_MAX], ""]
    example = example_markup(cfg.post_example) if cfg.post_example.strip() else ""
    system = SYSTEM.format(
        lang=LANG_NAMES.get(lang, lang),
        links=LINKS_ON if cfg.inline_links else LINKS_OFF,
        example=EXAMPLE.format(example) if example else "",
        instructions=f"\n\nEditor's instructions:\n{cfg.post_instructions.strip()}"
        if cfg.post_instructions.strip()
        else "",
    )
    return system, "\n".join(lines).strip()


def render_body(body: str, urls: list[str], links: bool) -> list[str]:
    """Разметка модели → абзацы Telegram HTML; [фраза](n) без такого источника — просто фраза."""

    def link(m: re.Match[str]) -> str:
        n = int(m.group(2))
        if links and 1 <= n <= len(urls) and urls[n - 1]:
            return f'<a href="{html.escape(urls[n - 1])}">{m.group(1)}</a>'
        return m.group(1)

    out = _BOLD.sub(r"<b>\1</b>", _LINK.sub(link, html.escape(body, quote=False)))
    return [p.strip() for p in re.split(r"\n\s*\n", out) if p.strip()][:MAX_PARAGRAPHS]


async def ai_post(pack: Any, lang: str, cfg: Any, llm: LlmProvider) -> str | None:
    """Telegram HTML поста; None — у события нет источников."""
    if not pack.sources:
        return None
    system, user = post_prompt(pack, lang, cfg)
    out = await llm.complete_json(system, user, AiPost)
    srcs = pack.sources[:MAX_SOURCES]
    emoji = cfg.emojis.get(pack.sport_id or "")
    head = html.escape(f"{emoji} {out.headline}" if emoji else out.headline, quote=False)
    parts = [f"<b>{head}</b>", *render_body(out.body, [s.url for s in srcs], cfg.inline_links)]
    names = [*competition_for(pack, lang), *pack.team_names]
    tags = [h for h in dict.fromkeys(hashtag(n) for n in names) if HASHTAG.match(h)]
    tags = tags[: cfg.max_hashtags]
    if tags:
        parts.append(" ".join(tags))
    main = srcs[0]
    if cfg.include_source_link and main.url:
        name = html.escape(main.source_name, quote=False)
        parts.append(f'<a href="{html.escape(main.url)}">{name}</a>')
    return "\n\n".join(parts)
