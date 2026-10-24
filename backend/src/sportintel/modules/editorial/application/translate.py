"""Перевод ИИ на язык интерфейса (ru/en): заголовки и сводки событий, черновики постов.

Одинаковый текст на тот же язык переводится один раз — результат лежит в кеше (editorial.translations).
"""

import hashlib
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any, Protocol

import structlog
from pydantic import BaseModel

from sportintel.modules.events import public as events
from sportintel.platform import ai_usage, jobs, settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.config import Settings
from sportintel.platform.db import Database, UnitOfWork
from sportintel.platform.llm import LlmProvider, make_provider

_log = structlog.get_logger("sportintel.editorial")
LANG_NAMES = {"ru": "Russian", "en": "English"}
WINDOW = timedelta(hours=72)
RANK = {"HIGH": 3, "MEDIUM": 2, "LOW": 1}
BATCH = 20
_LETTER = re.compile(r"[^\W\d_]")
_CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")


class Translation(BaseModel):
    text: str


class EventText(BaseModel):
    title: str
    summary: str = ""


class Cache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def put(self, key: str, lang: str, text: str, model: str) -> None: ...


CacheFor = Callable[[UnitOfWork], Cache]

SYSTEM = """You are a professional news translator for a sports and iGaming newsroom.
Translate the user's text into {lang} the way a native {lang} news editor would write it:
natural and fluent, never word-for-word. Keep the meaning, tone and every fact exactly;
do not add, drop, explain or comment on anything.
Names of people, clubs and places: use the established {lang} spelling, otherwise transliterate
the WHOLE name (Andrés Gómez → Андрес Гомес in Russian). Never mix Latin and Cyrillic letters
inside one word. Brands usually written in Latin (1win, DraftKings, iGaming) stay in Latin.
Keep numbers, scores, dates and hashtags unchanged. Do not add anything that is not in the
source: no citation markers, no extra punctuation at the end of a headline.
{html}If the text is already in {lang}, return it unchanged.
{out}"""
OUT_TEXT = 'Put only the translation into "text".'
OUT_EVENT = 'The user sends JSON with "title" and "summary": translate both into the same fields.'
_MIXED = re.compile(r"(?=\w*[A-Za-z])(?=\w*[А-Яа-яЁё])\w+")
HTML_RULE = (
    "The text is Telegram HTML: keep every tag (<b>, <i>, <u>, <s>, <a href=...>, <code>, <pre>, "
    "<blockquote>, <tg-spoiler>) with its attributes exactly where it is; translate only the "
    "visible text.\n"
)


def already_in(text: str, lang: str) -> bool:
    """Русский узнаём по кириллице и не тратим вызов модели; английский решает модель."""
    if lang != "ru":
        return False
    letters = _LETTER.findall(_TAG.sub(" ", text))
    return bool(letters) and len(_CYRILLIC.findall("".join(letters))) / len(letters) >= 0.6


def cache_key(text: str, lang: str, html: bool) -> str:
    return hashlib.sha256(f"{lang}\n{int(html)}\n{text}".encode()).hexdigest()


async def translate(
    db: Database, cache_for: CacheFor, llm: LlmProvider, text: str, lang: str, *, html: bool = False
) -> str:
    if not text.strip() or already_in(text, lang):
        return text
    key = cache_key(text, lang, html)
    async with db.uow() as uow:
        cached = await cache_for(uow).get(key)
    if cached is not None:
        return cached
    system = SYSTEM.format(
        lang=LANG_NAMES.get(lang, lang), html=HTML_RULE if html else "", out=OUT_TEXT
    )
    out = (await llm.complete_json(system, text, Translation)).text.strip() or text
    async with db.uow() as uow:
        await cache_for(uow).put(key, lang, out, llm.model)
    return out


async def translate_pair(
    db: Database,
    cache_for: CacheFor,
    llm: LlmProvider,
    title: str,
    summary: str,
    lang: str,
    event_id: Any = None,
) -> tuple[str, str]:
    """Заголовок и сводка одним вызовом модели (вдвое быстрее); в кеш — по отдельности."""
    keys = cache_key(title, lang, False), cache_key(summary, lang, False)
    async with db.uow() as uow:
        hit = [await cache_for(uow).get(k) for k in keys]
    if hit[0] is not None and (hit[1] is not None or not summary):
        return hit[0], hit[1] or ""
    system = SYSTEM.format(lang=LANG_NAMES.get(lang, lang), html="", out=OUT_EVENT)
    user = EventText(title=title, summary=summary).model_dump_json()
    async with ai_usage.track(db, "translate", llm.model, event_id):
        out = await llm.complete_json(system, user, EventText)
        if lang == "ru" and _MIXED.search(out.title + " " + out.summary):
            out = await llm.complete_json(system, user, EventText)  # один повтор: «Андрés» и т.п.
    t, s = out.title.strip() or title, out.summary.strip() or summary
    async with db.uow() as uow:
        await cache_for(uow).put(keys[0], lang, t, llm.model)
        if summary:
            await cache_for(uow).put(keys[1], lang, s, llm.model)
    return t, s


async def translator_for(db: Database, settings: Settings) -> LlmProvider | None:
    routing: Any = await settings_store.get(db, "ai_routing")
    return make_provider(settings, routing.translation_model)


async def ui_language(db: Database) -> str:
    langs: Any = await settings_store.get(db, "languages")
    return str(langs.ui_language)


async def translate_event(
    db: Database,
    cache_for: CacheFor,
    llm: LlmProvider,
    event_id: Any,
    lang: str,
    clock: Clock,
    full: bool = True,
) -> bool:
    """Заголовок и сводка события, затем заголовки и лиды его статей → язык интерфейса.
    full=False (ниже languages.translate_min_relevance) — только заголовки: короткий вызов модели,
    но в списках не остаётся текста на языке источника. False — переводить уже нечего."""
    async with db.uow() as uow:
        rows = await events.translation_candidates(uow, lang, clock.now() - WINDOW, 1, event_id)
    if rows:
        row = rows[0]
        src = (row["summary"] or "") if full else ""
        if already_in(row["title"], lang) and already_in(src or row["title"], lang):
            title, text = row["title"], src  # уже на языке интерфейса — модель не нужна
        else:
            title, text = await translate_pair(
                db, cache_for, llm, row["title"], src, lang, event_id
            )
        summary = (hashlib.sha256(src.encode()).hexdigest(), text) if src else None
        async with db.uow() as uow:
            await events.set_translation(uow, event_id, lang, title, summary)
    n = await _translate_articles(db, cache_for, llm, event_id, lang, full)
    _log.info("editorial.event_translated", event_id=str(event_id), lang=lang, articles=n)
    return bool(rows) or n > 0


async def _translate_articles(
    db: Database, cache_for: CacheFor, llm: LlmProvider, event_id: Any, lang: str, full: bool
) -> int:
    """Каждая статья сохраняется сразу: карточки в UI переводятся по одной, а не все в конце.
    ponytail: без full лид не переводится и потом не догоняется — откроют событие, переведётся всё."""
    async with db.uow() as uow:
        todo = await events.articles_to_translate(uow, event_id, lang)
    for a in todo:
        lead = (a["lead"] or "") if full else ""
        if a["same_lang"] or already_in(a["title"] + " " + lead, lang):
            title, lead = a["title"], lead
        else:
            title, lead = await translate_pair(db, cache_for, llm, a["title"], lead, lang, event_id)
        async with db.uow() as uow:
            await events.set_article_translation(uow, a["id"], lang, title, lead or None)
    return len(todo)


async def backlog(db: Database, clock: Clock, limit: int = BATCH) -> list[dict[str, Any]]:
    """Свежие события без перевода на язык интерфейса — важные и новые первыми."""
    langs: Any = await settings_store.get(db, "languages")
    async with db.uow() as uow:
        return await events.translation_candidates(
            uow, langs.ui_language, clock.now() - WINDOW, limit,
            min_rank=RANK[langs.translate_min_relevance],
        )  # fmt: skip


async def enqueue_due(db: Database, clock: Clock) -> int:
    """Свежие события без перевода — в очередь перевода (важные и новые первыми)."""
    lang = await ui_language(db)
    rows = await backlog(db, clock)
    n = 0
    for r in rows:
        n += int(
            await jobs.enqueue(
                "editorial.translate_event",
                queueing_lock=f"translate:{r['id']}:{lang}",
                event_id=str(r["id"]),
                lang=lang,
                full=bool(r["full"]),
            )
        )
    return n
