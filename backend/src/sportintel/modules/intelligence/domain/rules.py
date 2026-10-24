"""Обогащение по правилам без LM (ADR-004, BE-T2.7). Чистые функции: только stdlib."""

import re
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sportintel.modules.intelligence.domain.enrich_output import (
    EnrichOutput,
    EntityMention,
    RelevanceOut,
)
from sportintel.modules.intelligence.domain.values import Relevance
from sportintel.platform.text import normalize_name

RATIONALE_MAX = 280


@dataclass(frozen=True)
class ArticleInput:
    url: str
    title: str
    lead: str | None
    text: str | None
    categories: tuple[str, ...]
    language: str | None
    published_at: datetime | None


@dataclass(frozen=True)
class Found:
    """Сущность справочника, найденная в тексте (taxonomy.find_mentions)."""

    entity_id: Any
    kind: str
    sport_id: str | None
    priority: int
    mention: str
    in_title: bool
    name: str


def _has(text_norm: str, phrase: str) -> bool:
    p = normalize_name(phrase)
    return bool(p) and re.search(rf"(?<!\w){re.escape(p)}(?!\w)", text_norm) is not None


def _sports_site(a: ArticleInput, rules: Any) -> bool:
    host = (urlsplit(a.url).hostname or "").removeprefix("www.")
    return host in getattr(rules, "sports_domains", [])


def _weak_names(a: ArticleInput, rules: Any) -> set[str]:
    if _sports_site(a, rules):  # на спортивном сайте «Santos» — клуб, а не город
        return set()
    return {normalize_name(n) for n in getattr(rules, "ambiguous_entities", [])}


def detect_sport(a: ArticleInput, rules: Any, found: list[Found]) -> tuple[str | None, str]:
    """URL раздела → категории RSS → ключевые слова → вид спорта найденных сущностей."""
    path = urlsplit(a.url).path.lower()
    for sport, patterns in rules.sport_url_patterns.items():
        if any(p.lower() in path for p in patterns):
            return sport, f"url:{sport}"
    for cat in a.categories:
        sport = rules.rss_category_map.get(normalize_name(cat))
        if sport:
            return sport, f"category:{sport}"
    # Сигналы: ключевые слова + разные сущности вида спорта из заголовка. Однозначная сущность (клуб) — достаточно;
    # иначе нужно ≥2 сигналов: одно «finalização» или «Internacional» в новости о Нобелевке — не спорт.
    body = normalize_name(f"{a.title} {a.lead or ''}")
    kw = {s: sum(_has(body, k) for k in kws) for s, kws in rules.sport_keywords.items()}
    weak = _weak_names(a, rules)
    strong: dict[str, set[str]] = {}
    ents: dict[str, set[str]] = {}
    for f in found:
        # Только заголовок: в тексте страницы бывают блоки «читайте также» с клубами и турнирами.
        if f.sport_id and f.in_title:
            ents.setdefault(f.sport_id, set()).add(f.name)
            if normalize_name(f.name) not in weak:
                strong.setdefault(f.sport_id, set()).add(f.name)
    signals = {s: kw.get(s, 0) + len(ents.get(s, ())) for s in kw.keys() | ents.keys()}
    ok = {s: n for s, n in signals.items() if strong.get(s) or n >= 2}
    best = sorted(ok.items(), key=lambda kv: -kv[1])
    if best and (len(best) == 1 or best[0][1] > best[1][1]):
        sport = best[0][0]
        return sport, f"keywords:{sport}" if kw.get(sport) else f"entities:{sport}"
    return None, "sport:unknown"


@dataclass(frozen=True)
class Part:
    """Слагаемое балла важности: что сработало, сколько дало и где нашлось."""

    kind: str  # rule | competition | team | rumor | clickbait
    name: str
    points: int
    where: str  # title | body | entity | text
    label: str  # метка в rationale, без языка: «rule:Травма(+6)»; текст собирает интерфейс


def relevance_parts(
    a: ArticleInput,
    rules: Any,
    found: list[Found],
    rumor: list[str],
    clickbait: bool = False,
) -> list[Part]:
    """Все слагаемые балла. Слово в заголовке — вес × 2, только в тексте — вес × body_weight."""
    title = normalize_name(a.title)
    body = normalize_name(f"{a.lead or ''} {(a.text or '')[:4000]}")
    parts: list[Part] = []
    for rule in rules.relevance_rules:
        words = rule.all_words
        if any(_has(title, k) for k in words):
            w = rule.weight * 2
            parts.append(Part("rule", rule.name, w, "title", f"rule:{rule.name}({w:+d})"))
        elif any(_has(body, k) for k in words):
            w = round(rule.weight * rules.body_weight)
            if w:
                parts.append(Part("rule", rule.name, w, "body", f"rule:{rule.name}({w:+d})"))
    comps = [f for f in found if f.kind == "competition"]
    if comps:
        top = max(comps, key=lambda f: f.priority)
        w = rules.competition_weight.get(top.name, top.priority)
        if w:
            label = f"competition:{top.name}({w:+d})"
            parts.append(Part("competition", top.name, w, "entity", label))
    teams = [f for f in found if f.kind == "team"]
    if teams and max(t.priority for t in teams) >= 2 and rules.top_team_bonus:
        b = rules.top_team_bonus
        best = max(teams, key=lambda t: t.priority)
        parts.append(Part("team", best.name, b, "entity", f"top_club:{best.name}(+{b})"))
    if rumor and rules.rumor_penalty:
        p = rules.rumor_penalty
        parts.append(Part("rumor", ", ".join(rumor[:3]), -p, "text", f"rumor:(-{p})"))
    # рубрика: высокий уровень не выставляется по кликбейту
    if clickbait and rules.clickbait_penalty:
        p = rules.clickbait_penalty
        parts.append(Part("clickbait", "", -p, "title", f"clickbait:(-{p})"))
    return parts


def level_for(score: int, rules: Any) -> Relevance:
    """Спортивный материал без сигналов — LOW; IRRELEVANT — только не про спорт (рубрика BE-T2.7)."""
    t = rules.level_thresholds
    if score >= t.HIGH:
        return Relevance.HIGH
    if score >= t.MEDIUM:
        return Relevance.MEDIUM
    return Relevance.LOW


def score_relevance(
    a: ArticleInput,
    rules: Any,
    found: list[Found],
    rumor: list[str],
    is_sports: bool,
    clickbait: bool = False,
) -> tuple[RelevanceOut, list[str]]:
    if not is_sports:
        return RelevanceOut(Relevance.IRRELEVANT, "rules: not_sports"), []
    parts = relevance_parts(a, rules, found, rumor, clickbait)
    applied = [p.label for p in parts]
    level = level_for(sum(p.points for p in parts), rules)
    rationale = "rules: " + (", ".join(applied) or "no_signals")
    return RelevanceOut(level, rationale[:RATIONALE_MAX]), applied


def explain(a: ArticleInput, rules: Any, found: list[Found]) -> dict[str, Any]:
    """Как правила оценили бы материал — по шагам, для экрана «Важность»."""
    sport, _ = detect_sport(a, rules, found)
    relevant = [f for f in found if sport is None or f.sport_id in (None, sport)]
    weak = _weak_names(a, rules)
    is_sports = (
        sport is not None
        or _sports_site(a, rules)
        or any(f.in_title and normalize_name(f.name) not in weak for f in relevant)
    )
    rumor = find_rumor_markers(a, rules)
    parts = relevance_parts(a, rules, relevant, rumor, is_clickbait(a.title, rules))
    score = sum(p.points for p in parts)
    level = level_for(score, rules) if is_sports else Relevance.IRRELEVANT
    return {
        "is_sports": is_sports,
        "sport": sport,
        "score": score,
        "level": level.value,
        "parts": [vars(p) for p in parts] if is_sports else [],
    }


def find_rumor_markers(a: ArticleInput, rules: Any) -> list[str]:
    body = normalize_name(f"{a.title} {a.lead or ''} {(a.text or '')[:4000]}")
    return [m for m in rules.all_rumor_markers if _has(body, m)][:10]


def is_clickbait(title: str, rules: Any) -> bool:
    return any(re.search(p, title) for p in rules.clickbait_patterns)


def enrich_by_rules(a: ArticleInput, rules: Any, found: list[Found]) -> EnrichOutput:
    sport, sport_reason = detect_sport(a, rules, found)
    relevant = [f for f in found if sport is None or f.sport_id in (None, sport)]
    comps = sorted(
        (f for f in relevant if f.kind == "competition"),
        key=lambda f: (-f.priority, not f.in_title),
    )
    weak = _weak_names(a, rules)  # омоним без вида спорта — не повод считать материал спортивным
    is_sports = (
        sport is not None
        or _sports_site(a, rules)
        or any(f.in_title and normalize_name(f.name) not in weak for f in relevant)
    )
    rumor = find_rumor_markers(a, rules)
    clickbait = is_clickbait(a.title, rules)
    relevance, applied = score_relevance(a, rules, relevant, rumor, is_sports, clickbait)
    entities = [
        EntityMention(
            f.mention, f.kind, "subject" if f.in_title else "mentioned", f.name, f.entity_id
        )
        for f in relevant
        if f.kind != "competition"
    ]
    competition = (
        EntityMention(
            comps[0].mention, "competition", "mentioned", comps[0].name, comps[0].entity_id
        )
        if comps
        else None
    )
    out = EnrichOutput(
        language=a.language or "pt-BR",
        is_sports=is_sports,
        sport=sport,
        competition=competition,
        entities=entities[:30],
        claims=[],  # claims извлекает только LM (фаза L) — без них нет конфликтов (ADR-004)
        rumor_markers=rumor,
        clickbait=clickbait,
        event_date_hint=None,
        headline_neutral=a.title,
        relevance=relevance,
        applied_rules=[sport_reason, *applied],
    )
    return postprocess_clean(out, a, active_sports=None)


def postprocess_clean(
    out: EnrichOutput, a: ArticleInput, active_sports: set[str] | None
) -> EnrichOutput:
    """Кодовая пост-валидация (BE-T2.7 §7), общая для правил и LM."""
    source_norm = normalize_name(f"{a.title} {a.lead or ''} {a.text or ''}")
    sport = out.sport if active_sports is None or out.sport in active_sports else None
    relevance = (
        out.relevance
        if out.is_sports
        else RelevanceOut(Relevance.IRRELEVANT, out.relevance.rationale)
    )
    claims = [
        c for c in out.claims if normalize_name(c.quote) and normalize_name(c.quote) in source_norm
    ]
    markers = [m for m in out.rumor_markers if normalize_name(m) in source_norm]
    hint: date | None = out.event_date_hint
    if hint and a.published_at and hint > (a.published_at + timedelta(days=1)).date():
        hint = None
    return replace(
        out,
        sport=sport,
        relevance=relevance,
        claims=claims,
        rumor_markers=markers,
        event_date_hint=hint,
        headline_neutral=out.headline_neutral.strip() or a.title,
    )
