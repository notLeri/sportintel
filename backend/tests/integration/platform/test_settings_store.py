from datetime import UTC, datetime

import pytest

from sportintel.platform import settings_store as ss
from sportintel.platform.db import Database

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _clear() -> None:
    ss.clear_cache()


async def test_defaults_without_row(db: Database) -> None:
    routing = await ss.get(db, "ai_routing")
    assert (routing.enrich_article, routing.telegram_draft, routing.embeddings) == (
        "rules",
        "template",
        "off",
    )
    assert (await ss.get(db, "clustering")).w_lex == 0.5
    assert (await ss.get(db, "drafts")).sport_emoji["football"] == "⚽"


async def test_put_validates_and_resets_cache(db: Database) -> None:
    assert (await ss.get(db, "content")).lead_max_chars == 500
    async with db.uow() as u:
        await ss.put(u, "content", {"lead_max_chars": 300}, None, NOW)
    assert (await ss.get(db, "content")).lead_max_chars == 300
    async with db.uow() as u:
        with pytest.raises(ss.InvalidSettingsValue) as e:
            await ss.put(u, "ai_routing", {"enrich_article": "magic"}, None, NOW)
    assert e.value.details[0].field == "enrich_article"


async def test_unknown_key(db: Database) -> None:
    with pytest.raises(ss.UnknownSettingsKey):
        await ss.get(db, "nope")
