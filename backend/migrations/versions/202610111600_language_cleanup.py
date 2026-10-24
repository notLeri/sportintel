"""Ни слова на португальском в интерфейсе: названия турниров для показа, обоснования важности
кодами (текст собирает интерфейс), сигналы важности — по-русски, их слова — по языкам источников

Revision ID: 202610111600
Revises: 202610111400
Create Date: 2026-10-11 16:00:00+00:00
"""

import json
import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "202610111600"
down_revision: str | None = "202610111400"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Турниры: название для показа (поиск в текстах — по-прежнему по canonical_name и алиасам)
COMPETITIONS = {
    "Brasileirão Série A": ("Чемпионат Бразилии, Серия A", "Brazilian Serie A"),
    "Brasileirão Série B": ("Чемпионат Бразилии, Серия B", "Brazilian Serie B"),
    "Copa do Brasil": ("Кубок Бразилии", "Brazil Cup"),
    "CONMEBOL Libertadores": ("Кубок Либертадорес", "Copa Libertadores"),
    "CONMEBOL Sul-Americana": ("Южноамериканский кубок", "Copa Sudamericana"),
    "Eliminatórias da Copa do Mundo": ("Отбор к чемпионату мира", "World Cup qualifiers"),
    "Seleção Brasileira": ("Сборная Бразилии", "Brazil national team"),
    "Copa do Mundo": ("Чемпионат мира", "World Cup"),
    "Fórmula 1": ("Формула-1", "Formula 1"),
    "Campeonato Paulista": ("Чемпионат штата Сан-Паулу", "São Paulo State Championship"),
    "Campeonato Carioca": ("Чемпионат штата Рио-де-Жанейро", "Rio de Janeiro State Championship"),
    "Campeonato Mineiro": ("Чемпионат штата Минас-Жерайс", "Minas Gerais State Championship"),
    "Campeonato Gaúcho": (
        "Чемпионат штата Риу-Гранди-ду-Сул",
        "Rio Grande do Sul State Championship",
    ),
    "Superliga": ("Суперлига Бразилии по волейболу", "Brazilian Volleyball Superliga"),
    "NBB": ("НББ — чемпионат Бразилии по баскетболу", "NBB — Brazilian basketball league"),
    "UFC": ("UFC", "UFC"),
    "ATP": ("ATP", "ATP"),
    "WTA": ("WTA", "WTA"),
}

# Прежние названия сигналов (pt и «ru/en») → одно русское
RULE_NAMES = {
    "lesão": "Травма", "травма/injury": "Травма",
    "suspensão": "Дисквалификация", "дисквалификация/suspension": "Дисквалификация",
    "escalação": "Состав на матч",
    "técnico": "Смена тренера", "тренер/coach": "Смена тренера",
    "partida": "Перенос или условия матча",
    "decisão": "Решающий матч", "финал/final": "Решающий матч",
    "convocação": "Вызов в сборную",
    "doping": "Допинг",
    "transferência": "Трансфер", "трансфер/transfer": "Трансфер",
    "resultado": "Результат", "результат/result": "Результат",
    "jogo próximo": "Ближайший матч",
    "evento principal": "Главный бой",
    "fora de campo": "Вне поля",
    "регулирование/regulation": "Регулирование",
    "праздник/holiday": "Праздник",
}  # fmt: skip
MODIFIERS = {
    "priority_up": [
        " · Prioridade: torneio/clube de destaque",
        " · Priority: top competition/club",
        " · Приоритет: топ-турнир/клуб",
    ],
    "priority_down": [
        " · Torneio de baixa prioridade",
        " · Low-priority competition",
        " · Турнир низкого приоритета",
    ],
    "stale": [" · Possível notícia antiga", " · Possibly old news", " · Возможно, старая новость"],
}
TOKEN = re.compile(r"^(.*)\(([+-]\d+)\)$")
CYRILLIC = re.compile(r"[а-яё]", re.IGNORECASE)


def rationale(s: str) -> str:
    """Прежний текст обоснования → коды: «rules: rule:Травма(+6), top_club:(+1) · stale»."""
    mods = ""
    for code, texts in MODIFIERS.items():
        for x in texts:
            if x in s:
                s = s.replace(x, "")
                mods += f" · {code}"
    if not s.startswith("rules: "):
        return s + mods
    body = s[len("rules: ") :]
    if body == "sem fato esportivo":
        return "rules: not_sports" + mods
    if body == "sem sinais":
        return "rules: no_signals" + mods
    out: dict[str, int] = {}
    for raw in body.split(", "):
        m = TOKEN.match(raw.strip())
        if not m:
            continue  # обрезанный хвост
        name, pts = m.group(1), int(m.group(2))
        if name == "clube da Série A":
            key = "top_club:"
        elif name in ("rumor", "clickbait"):
            key = f"{name}:"
        elif name in RULE_NAMES:
            key = f"rule:{RULE_NAMES[name]}"
        else:
            key = f"competition:{name}"
        out[key] = out.get(key, 0) + pts  # два прежних сигнала стали одним — баллы суммой
    tokens = ", ".join(f"{k}({v:+d})" for k, v in out.items())
    return "rules: " + (tokens or "no_signals") + mods


def rules_value(v: dict[str, Any]) -> dict[str, Any]:
    merged: dict[str, dict[str, Any]] = {}
    for r in v.get("relevance_rules", []):
        old = r["name"]
        name = RULE_NAMES.get(old, old)
        latin = "en" if "/" in old else "pt-BR"
        words = r.get("words") or {}
        for w in r.get("keywords", []):
            words.setdefault("ru" if CYRILLIC.search(w) else latin, []).append(w)
        m = merged.setdefault(name, {"name": name, "weight": r["weight"], "words": {}})
        for lang, ws in words.items():
            m["words"].setdefault(lang, []).extend(
                x for x in ws if x not in m["words"].get(lang, [])
            )
    out = {**v, "relevance_rules": list(merged.values())}
    if isinstance(v.get("rumor_markers"), list):
        rm: dict[str, list[str]] = {}
        for w in v["rumor_markers"]:
            rm.setdefault("ru" if CYRILLIC.search(w) else "pt-BR", []).append(w)
        out["rumor_markers"] = rm
    return out


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("name_i18n", pg.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        schema="taxonomy",
    )
    bind = op.get_bind()
    for canonical, (ru, en) in COMPETITIONS.items():
        bind.execute(
            sa.text(
                "UPDATE taxonomy.entities SET name_i18n = CAST(:v AS jsonb)"
                " WHERE kind = 'competition' AND canonical_name = :c"
            ),
            {"v": json.dumps({"ru": ru, "en": en}, ensure_ascii=False), "c": canonical},
        )
    for table in ("events.events", "intelligence.article_enrichments"):
        olds = bind.execute(
            sa.text(f"SELECT DISTINCT relevance_rationale FROM {table}")  # noqa: S608 — константа
        ).scalars()
        for old in [o for o in olds if o]:
            new = rationale(old)
            if new != old:
                bind.execute(
                    sa.text(
                        f"UPDATE {table} SET relevance_rationale = :n WHERE relevance_rationale = :o"  # noqa: S608 — константа
                    ),
                    {"n": new, "o": old},
                )
    row = bind.execute(
        sa.text("SELECT value FROM platform.app_settings WHERE key = 'enrich_rules'")
    ).scalar()
    if row:
        bind.execute(
            sa.text(
                "UPDATE platform.app_settings SET value = CAST(:v AS jsonb) WHERE key = 'enrich_rules'"
            ),
            {"v": json.dumps(rules_value(row), ensure_ascii=False)},
        )


def downgrade() -> None:
    op.drop_column("entities", "name_i18n", schema="taxonomy")
