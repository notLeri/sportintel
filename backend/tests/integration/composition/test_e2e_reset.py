from sqlalchemy import text
from tests.factories import make_article, make_event, make_source

from sportintel.composition.e2e_cli import reset
from sportintel.platform.db import Database


async def test_reset_wipes_data_and_seeds_users_and_sources(db: Database) -> None:
    async with db.uow() as u:
        await make_event(u, [await make_article(u, await make_source(u))])
        teams = (await u.session.execute(text("SELECT count(*) FROM taxonomy.entities"))).scalar()
    await reset(db)
    await reset(db)  # идемпотентно
    async with db.uow() as u:
        q = lambda sql: u.session.execute(text(sql))  # noqa: E731
        assert (await q("SELECT count(*) FROM events.events")).scalar() == 0
        assert sorted(r[0] for r in await q("SELECT email FROM identity.users")) == [
            "admin@e2e.test",
            "editor@e2e.test",
            "researcher@e2e.test",
        ]
        assert sorted(r[0] for r in await q("SELECT domain FROM sources.sources")) == [
            "espn.e2e.test",
            "globo.e2e.test",
            "uol.e2e.test",
        ]
        assert (await q("SELECT count(*) FROM taxonomy.entities")).scalar() == teams
