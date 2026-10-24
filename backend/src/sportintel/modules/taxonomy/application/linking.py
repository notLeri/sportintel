"""Связывание упоминаний со справочником и поиск алиасов в тексте (BE-T2.2, ADR-004)."""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

import structlog

from sportintel.modules.taxonomy.domain.linking import Candidate, choose, is_ambiguous
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.platform.text import normalize_name

# ponytail: константы вместо app_settings.entity_linking (BE-T2.3 core переносит в настройки).
TRIGRAM_THRESHOLD = 0.45
AUTO_CREATE_PLAYERS = True
TRIGRAM_MARGIN = 0.05
MAX_NGRAM = 4
_TOKEN = re.compile(r"[\w'’-]+", re.UNICODE)
_log = structlog.get_logger("sportintel.taxonomy")

Method = Literal["exact", "trigram", "auto_created", "unlinked"]


@dataclass(frozen=True)
class Mention:
    text: str
    kind: EntityKind
    sport_id: str | None
    canonical_guess: str | None = None


@dataclass(frozen=True)
class LinkResult:
    mention: Mention
    entity_id: uuid.UUID | None
    method: Method
    confidence: float


@dataclass(frozen=True)
class FoundEntity:
    entity_id: uuid.UUID
    kind: EntityKind
    sport_id: str | None
    priority: int
    mention: str
    start: int


class LinkStore(Protocol):
    async def exact(self, keys: list[str]) -> list[Candidate]: ...
    async def trigram(
        self, key: str, kind: str, sport_id: str | None, threshold: float
    ) -> list[Candidate]: ...
    async def create_player(self, name: str, sport_id: str) -> uuid.UUID: ...
    async def upsert_unlinked(
        self, mention: Mention, norm: str, now: datetime, sample_article_id: uuid.UUID | None
    ) -> None: ...


def _sport_ok(c: Candidate, sport_id: str | None) -> bool:
    return c.sport_id is None or sport_id is None or c.sport_id == sport_id


async def link_entities(
    store: LinkStore,
    mentions: list[Mention],
    now: datetime,
    sample_article_id: uuid.UUID | None = None,
) -> list[LinkResult]:
    keyed = [
        (
            m,
            {normalize_name(m.text)}
            | ({normalize_name(m.canonical_guess)} if m.canonical_guess else set()),
        )
        for m in mentions
    ]
    all_keys = sorted({k for _, keys in keyed for k in keys if 2 <= len(k) <= 100})
    exact = await store.exact(all_keys) if all_keys else []
    results: list[LinkResult] = []
    linked: set[uuid.UUID] = set()
    for mention, keys in keyed:
        norm = normalize_name(mention.text)
        if not 2 <= len(norm) <= 100:
            results.append(LinkResult(mention, None, "unlinked", 0.0))
            continue
        cands = [
            c
            for c in exact
            if c.matched_alias_norm in keys
            and c.kind == mention.kind.value
            and _sport_ok(c, mention.sport_id)
        ]
        if cands:
            best = choose(cands, linked, mention.sport_id)
            assert best is not None  # noqa: S101
            ambiguous = is_ambiguous(cands, best, mention.sport_id)
            if ambiguous:
                _log.info("taxonomy.ambiguous_link", mention_norm=norm, candidates=len(cands))
            linked.add(best.entity_id)
            results.append(LinkResult(mention, best.entity_id, "exact", 0.5 if ambiguous else 1.0))
            continue
        tri = [
            c
            for c in await store.trigram(
                norm, mention.kind.value, mention.sport_id, TRIGRAM_THRESHOLD
            )
            if _sport_ok(c, mention.sport_id)
        ][:2]
        if tri and (len(tri) == 1 or tri[0].similarity - tri[1].similarity >= TRIGRAM_MARGIN):
            linked.add(tri[0].entity_id)
            results.append(LinkResult(mention, tri[0].entity_id, "trigram", tri[0].similarity))
            continue
        if mention.kind == EntityKind.PLAYER and mention.sport_id and AUTO_CREATE_PLAYERS:
            entity_id = await store.create_player(mention.text.strip(), mention.sport_id)
            results.append(LinkResult(mention, entity_id, "auto_created", 0.6))
            continue
        await store.upsert_unlinked(mention, norm, now, sample_article_id)
        results.append(LinkResult(mention, None, "unlinked", 0.0))
    return results


def _ngrams(text: str) -> list[tuple[str, int, int, bool]]:
    """(норм. n-грамма, начало, конец, начинается с заглавной) для n = MAX_NGRAM…1."""
    tokens = [(m.group(0), m.start(), m.end()) for m in _TOKEN.finditer(text)]
    out = []
    for n in range(MAX_NGRAM, 0, -1):
        for i in range(len(tokens) - n + 1):
            chunk = tokens[i : i + n]
            out.append(
                (
                    normalize_name(" ".join(t for t, _, _ in chunk)),
                    chunk[0][1],
                    chunk[-1][2],
                    chunk[0][0][:1].isupper(),
                )
            )
    return out


async def find_mentions(
    store: LinkStore, text: str, sport_id: str | None = None
) -> list[FoundEntity]:
    """Алиасы справочника в тексте без LM (ADR-004): точное совпадение n-грамм, длинные — первыми,
    без пересечений. ponytail: только имена с заглавной буквы — иначе «sport», «leão», «galo»
    срабатывают на обычных словах; контекстное разрешение — LM (фаза L)."""
    grams = [g for g in _ngrams(text) if g[3] and 2 <= len(g[0]) <= 100]
    if not grams:
        return []
    by_alias: dict[str, list[Candidate]] = {}
    for c in await store.exact(sorted({g[0] for g in grams})):
        by_alias.setdefault(c.matched_alias_norm, []).append(c)
    taken: list[tuple[int, int]] = []
    found: list[FoundEntity] = []
    seen: set[uuid.UUID] = set()
    for norm, start, end, _ in grams:  # уже по убыванию длины n-граммы
        cands = [c for c in by_alias.get(norm, []) if _sport_ok(c, sport_id)]
        if not cands or any(s < end and start < e for s, e in taken):
            continue
        best = choose(cands, seen, sport_id)
        assert best is not None  # noqa: S101
        taken.append((start, end))
        if best.entity_id not in seen:
            seen.add(best.entity_id)
            found.append(
                FoundEntity(
                    best.entity_id,
                    EntityKind(best.kind),
                    best.sport_id,
                    best.priority,
                    text[start:end],
                    start,
                )
            )
    return sorted(found, key=lambda f: f.start)
