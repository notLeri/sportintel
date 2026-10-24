from datetime import UTC, datetime

import pytest
from tests.factories import make_article, make_entity, make_event, make_source

from sportintel.modules.events.domain.actor import SYSTEM
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AttachMethod,
    OverrideField,
    RelationKind,
)
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.platform.db import Database
from sportintel.platform.errors import ConcurrencyConflict

NOW = datetime(2026, 10, 8, 12, tzinfo=UTC)


async def test_roundtrip_save_links_and_version(db: Database) -> None:
    async with db.uow() as u:
        s = await make_source(u, domain="ev.example.com")
        a, b, c = await make_article(u, s), await make_article(u, s), await make_article(u, s)
        e = await make_event(u, [a, b])
        repo = SqlEventRepository(u.session)
        got = await repo.get(e.id)
        assert got is not None
        assert ([lk.article_id for lk in got.links], got.version) == ([a.id, b.id], 1)
        got.edit(SYSTEM, NOW, title="Título novo")
        got.detach(a.id, NOW)
        got.attach(ArticleLink(c.id, NOW, 0.8, AttachMethod.AUTO), NOW)
        await repo.save(got, 1)
        again = await repo.get(e.id, for_update=True)
        assert again is not None
        assert (again.title, again.version, {lk.article_id for lk in again.links}) == (
            "Título novo",
            2,
            {b.id, c.id},
        )
        assert OverrideField.TITLE in again.manual_overrides
        with pytest.raises(ConcurrencyConflict):
            await repo.save(again, 1)
        assert await repo.event_ids_for_articles([b.id, c.id, a.id]) == {b.id: e.id, c.id: e.id}
        assert await repo.event_id_for_article(a.id) is None


async def test_entities_and_relations(db: Database) -> None:
    async with db.uow() as u:
        s = await make_source(u, domain="ev2.example.com")
        e1 = await make_event(u, [await make_article(u, s)])
        e2 = await make_event(u, [await make_article(u, s)])
        team = await make_entity(u, "Time Teste")
        repo = SqlEventRepository(u.session)
        await repo.replace_entities(e1.id, [(team.id, "team", 2, False)])
        await repo.replace_relations(
            e1.id, RelationKind.POSSIBLE_DUPLICATE, [(e2.id, 0.7), (e1.id, 1.0)]
        )
        got = await repo.get(e1.id)
    assert got is not None
    assert got.entities == [(team.id, "team")]
