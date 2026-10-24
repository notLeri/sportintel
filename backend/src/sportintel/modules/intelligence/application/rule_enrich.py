"""Обогащение по правилам: правила из app_settings + сущности через taxonomy (BE-T2.7)."""

from typing import Any

from sportintel.modules.intelligence.application.seed_rules import SEED_ENRICH_RULES
from sportintel.modules.intelligence.domain.enrich_output import EnrichOutput
from sportintel.modules.intelligence.domain.rules import ArticleInput, Found, enrich_by_rules
from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform import settings_store
from sportintel.platform.db import Database, UnitOfWork

# Seed правил — значение по умолчанию ключа enrich_rules (пока admin не сохранил свои).
settings_store.DEFAULT_OVERRIDES["enrich_rules"] = SEED_ENRICH_RULES


async def find_entities(uow: UnitOfWork, a: ArticleInput) -> list[Found]:
    in_title = await taxonomy.find_mentions(uow, a.title)
    body = await taxonomy.find_mentions(uow, f"{a.lead or ''}\n{(a.text or '')[:4000]}")
    title_ids = {f.entity_id for f in in_title}
    found = [
        Found(f.entity_id, f.kind.value, f.sport_id, f.priority, f.mention, True, f.mention)
        for f in in_title
    ]
    found += [
        Found(f.entity_id, f.kind.value, f.sport_id, f.priority, f.mention, False, f.mention)
        for f in body
        if f.entity_id not in title_ids
    ]
    names = await taxonomy.get_entities(uow, [f.entity_id for f in found])
    return [
        Found(**{**f.__dict__, "name": names[f.entity_id].name}) if f.entity_id in names else f
        for f in found
    ]


async def enrich_with_rules(db: Database, uow: UnitOfWork, a: ArticleInput) -> EnrichOutput:
    rules: Any = await settings_store.get(db, "enrich_rules")
    return enrich_by_rules(a, rules, await find_entities(uow, a))
