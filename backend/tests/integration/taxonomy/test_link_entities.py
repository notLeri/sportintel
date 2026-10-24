from datetime import UTC, datetime

from sqlalchemy import text

from sportintel.modules.taxonomy import public as taxonomy
from sportintel.modules.taxonomy.public import EntityKind as K
from sportintel.modules.taxonomy.public import Mention
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

CLOCK = FrozenClock(datetime(2026, 10, 8, 12, tzinfo=UTC))


async def names(db: Database, ids) -> list[str | None]:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        got = await taxonomy.get_entities(u, [i for i in ids if i])
    return [got[i].name if i else None for i in ids]


async def test_link_table(db: Database) -> None:
    mentions = [
        Mention("Mengão", K.TEAM, "football"),
        Mention("Flamengo RJ", K.TEAM, "football"),
        Mention("Timão", K.TEAM, None),
        Mention("o Verdão", K.TEAM, "football", canonical_guess="Palmeiras"),
        Mention("Liberta", K.COMPETITION, "football"),
        Mention("Palmeiras", K.TEAM, "basketball"),
        Mention("Zé Desconhecido", K.PLAYER, "football"),
        Mention("Técnico X", K.COACH, "football"),
        Mention("A", K.TEAM, "football"),
    ]
    async with db.uow() as u:
        res = await taxonomy.link_entities(u, mentions, CLOCK)
    assert [r.method for r in res] == [
        "exact",
        "trigram",
        "exact",
        "exact",
        "exact",
        "unlinked",
        "auto_created",
        "unlinked",
        "unlinked",
    ]
    assert await names(db, [r.entity_id for r in res]) == [
        "Flamengo",
        "Flamengo",
        "Corinthians",
        "Palmeiras",
        "CONMEBOL Libertadores",
        None,
        "Zé Desconhecido",
        None,
        None,
    ]

    async with db.uow() as u:  # повтор: тот же игрок, растут occurrences
        again = await taxonomy.link_entities(u, [mentions[6], mentions[7]], CLOCK)
        occ = (
            await u.session.execute(
                text(
                    "SELECT occurrences FROM taxonomy.unlinked_mentions WHERE mention_norm='tecnico x'"
                )
            )
        ).scalar()
        state = (
            await u.session.execute(
                text("SELECT review_state FROM taxonomy.entities WHERE id=:i"),
                {"i": res[6].entity_id},
            )
        ).scalar()
    assert again[0].entity_id == res[6].entity_id
    assert (occ, state) == (2, "pending")


async def test_find_mentions_in_text(db: Database) -> None:
    title = "Mengão vence o Palmeiras e assume a liderança do Brasileirão"
    body = "O time do Leão, sem leão nenhum, falou da sport e do Galo. Atlético-MG joga na Libertadores."
    async with db.uow() as u:
        in_title = await taxonomy.find_mentions(u, title, "football")
        in_body = await taxonomy.find_mentions(u, body, "football")
    assert [(f.mention, f.kind.value) for f in in_title] == [
        ("Mengão", "team"),
        ("Palmeiras", "team"),
        ("Brasileirão", "competition"),
    ]
    assert "sport" not in [f.mention for f in in_body]  # строчное слово — не имя
    found = set(await names(db, [f.entity_id for f in in_body]))
    assert {
        "Atlético Mineiro",
        "CONMEBOL Libertadores",
    } <= found  # «Galo» и «Atlético-MG» — одна сущность
