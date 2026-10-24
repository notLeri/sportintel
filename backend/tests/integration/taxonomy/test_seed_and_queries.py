from sqlalchemy import text
from tests.factories import make_entity

from sportintel.modules.taxonomy import public as taxonomy
from sportintel.platform.db import Database


async def q(db: Database, sql: str) -> object:
    async with db.uow() as u:
        return (await u.session.execute(text(sql))).scalar()


async def test_seed_counts(db: Database) -> None:
    assert await q(db, "SELECT count(*) FROM taxonomy.sports") == 10
    assert await q(db, "SELECT count(*) FROM taxonomy.entities WHERE kind='competition'") >= 12  # type: ignore[operator]
    assert await q(db, "SELECT count(*) FROM taxonomy.entities WHERE kind='team'") >= 40  # type: ignore[operator]
    # у каждой сущности есть алиас = canonical_name
    assert (
        await q(
            db,
            "SELECT count(*) FROM taxonomy.entities e WHERE NOT EXISTS (SELECT 1 FROM taxonomy.entity_aliases a WHERE a.entity_id=e.id AND a.alias=e.canonical_name)",
        )
        == 0
    )
    assert (
        await q(
            db,
            "SELECT e.canonical_name FROM taxonomy.entity_aliases a JOIN taxonomy.entities e ON e.id=a.entity_id WHERE a.alias_norm='mengao'",
        )
        == "Flamengo"
    )


async def test_facade(db: Database) -> None:
    async with db.uow() as u:
        sports = await taxonomy.list_sports(u)
        assert sports[0].id == "football"
        assert sports[-1].id == "other"
        assert sports[0].name_i18n == {"pt-BR": "Futebol", "en": "Football", "ru": "Футбол"}
        a = await make_entity(u, "Flamengo", sport_id="basketball", aliases=["Fla Basquete"])
        b = await make_entity(u, "Pedro", kind=taxonomy.EntityKind.PLAYER)
        got = await taxonomy.get_entities(u, [a.id, b.id])
        assert {e.name for e in got.values()} == {"Flamengo", "Pedro"}
        comps = await taxonomy.competition_aliases_for_prompt(u)
        assert (
            "CONMEBOL Libertadores",
            ["Copa Libertadores", "Liberta", "Libertadores"],
            "football",
        ) in comps
