"""Отбор фрагментов evidence pack (BE-T2.19). Чистая функция."""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime

FRAGMENT_MAX = 600
TIER_ORDER = {"OFFICIAL": 0, "A": 1, "B": 2, "C": 3}
_WORD = re.compile(r"\w+")


@dataclass(frozen=True)
class ArticleEvidence:
    article_id: uuid.UUID
    source_name: str
    source_tier: str | None
    published_at: datetime
    title: str
    lead: str | None
    text: str | None
    quotes: tuple[str, ...] = ()


@dataclass(frozen=True)
class EvidenceFragment:
    n: int
    article_id: uuid.UUID
    source_name: str
    source_tier: str | None
    published_at: datetime
    text: str


def _clip(s: str) -> str:
    s = " ".join(s.split())
    return s if len(s) <= FRAGMENT_MAX else s[: FRAGMENT_MAX - 1].rstrip() + "…"


def _paragraphs(a: ArticleEvidence) -> list[str]:
    paras = [p.strip() for p in (a.text or "").split("\n") if p.strip()]
    if a.lead and paras and " ".join(paras[0].split()) == " ".join(a.lead.split()):
        paras = paras[1:]
    if a.quotes:
        words = {w.lower() for q in a.quotes for w in _WORD.findall(q)}
        paras = sorted(paras, key=lambda p: -len(words & {w.lower() for w in _WORD.findall(p)}))
    return paras[:2]


def select_fragments(articles: list[ArticleEvidence], max_fragments: int) -> list[EvidenceFragment]:
    ordered = sorted(
        articles, key=lambda a: (TIER_ORDER.get(a.source_tier or "", 4), a.published_at)
    )
    queues = [
        [_clip(f"{a.title}. {a.lead}" if a.lead else a.title), *(_clip(p) for p in _paragraphs(a))]
        for a in ordered
    ]
    picked: list[tuple[ArticleEvidence, str]] = []
    depth = 0
    while len(picked) < max_fragments and any(
        depth < len(q) for q in queues
    ):  # round-robin по статьям
        for a, q in zip(ordered, queues, strict=True):
            if depth < len(q) and len(picked) < max_fragments:
                picked.append((a, q[depth]))
        depth += 1
    return [
        EvidenceFragment(n, a.article_id, a.source_name, a.source_tier, a.published_at, text)
        for n, (a, text) in enumerate(picked, start=1)
    ]
