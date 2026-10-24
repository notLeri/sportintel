"""Event brief (формат руководства): что произошло, статус, суть, кого касается, влияние, что делать, источники.

Модель не пишет ссылок: она выбирает номера статей события, ссылки подставляет код (grounding).
"""

import html
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

PROMPT_VERSION = "brief/v3"
MAX_SOURCES = 8
LEAD_MAX = 700

Status = Literal["official", "confirmed", "reported", "rumor"]
LANG_NAMES = {"ru": "Russian", "en": "English", "pt-BR": "Brazilian Portuguese"}


class EventBrief(BaseModel):
    """Схема ответа модели (constrained decoding в Ollama / tool input в Anthropic)."""

    # Даты нет: модель её выдумывала (eval 2026-10-09) — дату события подставляет код.
    headline: str = Field(max_length=140, description="What happened, one line")
    status: Status = Field(
        description="official: announced by club/league/federation; confirmed: several reliable "
        "outlets report it as fact; reported: one outlet reports it; rumor: speculation"
    )
    summary: list[str] = Field(
        min_length=1, max_length=5, description="3-5 short complete sentences, each ending with '.'"
    )
    affected: list[str] = Field(
        min_length=1, max_length=6, description="Names of clubs, players, competitions affected"
    )
    impact: str = Field(
        min_length=20,
        max_length=500,
        description="One or two full sentences: what this changes for the next match, the team "
        "or the betting market. Never a single word like 'high' or 'medium'.",
    )
    actions: list[str] = Field(
        min_length=1,
        max_length=3,
        description="Concrete next steps for an editor or a trader, e.g. what to monitor",
    )
    source_refs: list[int] = Field(
        min_length=1, max_length=5, description="Numbers [n] of the sources that support the brief"
    )


@dataclass(frozen=True)
class BriefSource:
    n: int
    name: str
    tier: str | None
    url: str


SYSTEM = """You are a sports news analyst for a betting company's editorial team.
You get numbered news articles (in any language) about ONE event. Write a factual brief.
LANGUAGE: every text field — headline, summary, affected, impact, actions — MUST be written in {lang}.
Never answer in English unless {lang} is English. Keep only proper names in their original spelling.
Rules:
- Use ONLY facts from the articles. Never invent or change names, numbers, dates or quotes.
  Copy club and player names exactly as they appear in the articles.
- If the articles disagree or the news is unconfirmed, choose status accordingly. The status is
  shown to the editor only: never write in the text fields whether the news is confirmed,
  official, reported or a rumor.
- source_refs: numbers of the articles that support the brief (most reliable first).
- Do not mention source names, trust tiers or article numbers in the text fields.
- impact: one or two sentences on what changes for the next match, the team's form or the betting
  odds (e.g. "Without the starting striker the team loses its main goal threat in the derby").
- actions: 1-3 concrete things an editor or trader should do or watch next
  (e.g. "Check the official line-up on match day", "Watch the odds on the derby").
- Be concise. No marketing tone, no emojis."""


def brief_prompt(pack: Any, lang: str) -> tuple[str, str, list[BriefSource]]:
    """→ (system, user, источники по номерам). Источники — из evidence pack, OFFICIAL/A первыми."""
    srcs = pack.sources[:MAX_SOURCES]
    frag = {f.article_id: f.text for f in getattr(pack, "fragments", [])}
    lines = [f"Event title: {pack.title}", ""]
    numbered = []
    for i, s in enumerate(srcs, 1):
        numbered.append(BriefSource(i, s.source_name, s.tier, s.url))
        body = (frag.get(s.article_id) or s.lead or "")[:LEAD_MAX]
        lines.append(f"[{i}] {s.source_name} (trust tier: {s.tier or 'unknown'})")
        lines.append(f"Title: {s.title}")
        if body:
            lines.append(f"Text: {body}")
        lines.append("")
    system = SYSTEM.format(lang=LANG_NAMES.get(lang, lang))
    return system, "\n".join(lines).strip(), numbered


def ground(brief: EventBrief, sources: list[BriefSource]) -> EventBrief | None:
    """Оставить только существующие номера источников; None — опереться не на что.

    «Подтверждено» требует ≥2 разных изданий среди опор, иначе честно «сообщает одно СМИ»."""
    refs = list(dict.fromkeys(r for r in brief.source_refs if 1 <= r <= len(sources)))
    if not refs:
        return None
    status = brief.status
    if status == "confirmed" and len({sources[r - 1].name for r in refs}) < 2:
        status = "reported"
    return brief.model_copy(update={"source_refs": refs, "status": status})


LABELS = {
    "ru": {
        "affected": "Кого касается",
        "impact": "Влияние",
        "actions": "Что делать",
        "sources": "Источники",
    },
    "en": {
        "affected": "Who is affected",
        "impact": "Impact",
        "actions": "What to do",
        "sources": "Sources",
    },
    "pt-BR": {
        "affected": "Quem é afetado",
        "impact": "Impacto",
        "actions": "O que fazer",
        "sources": "Fontes",
    },
}


def e(s: str) -> str:
    return html.escape(s, quote=False)


def render_tg(
    brief: EventBrief,
    sources: list[BriefSource],
    lang: str,
    emoji: str | None,
    event_date: str | None = None,
) -> str:
    """Telegram HTML. Ссылки — только из sources по source_refs.

    Статус (официально/подтверждено/слух) в пост не пишется: он для редактора (карточка брифа)."""
    lab = LABELS.get(lang, LABELS["en"])
    by_n = {s.n: s for s in sources}
    head = f"{emoji} {brief.headline}" if emoji else brief.headline
    parts = [f"<b>{e(head)}</b>"]
    if event_date:
        parts.append(f"<i>{e(event_date)}</i>")
    parts.append(e(" ".join(brief.summary)))
    if brief.affected:
        parts.append(f"<b>{e(lab['affected'])}:</b> {e(', '.join(brief.affected))}")
    if brief.impact:
        parts.append(f"<b>{e(lab['impact'])}:</b> {e(brief.impact)}")
    if brief.actions:
        parts.append(
            f"<b>{e(lab['actions'])}:</b>\n" + "\n".join(f"• {e(a)}" for a in brief.actions)
        )
    links = [
        f'<a href="{html.escape(by_n[n].url)}">{e(by_n[n].name)}</a>'
        for n in brief.source_refs
        if n in by_n and by_n[n].url
    ]
    if links:
        parts.append(f"{e(lab['sources'])}: " + ", ".join(links))
    return "\n\n".join(parts)
