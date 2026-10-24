import asyncio

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from sportintel.main import create_app
from sportintel.platform.config import Settings
from sportintel.platform.db import Database, UnitOfWork, head_revision

SCHEMAS = {
    "identity",
    "sources",
    "ingestion",
    "taxonomy",
    "intelligence",
    "events",
    "editorial",
    "audit",
    "analytics",
    "platform",
}


async def test_schemas_and_extensions(uow: UnitOfWork) -> None:
    schemas = set((await uow.session.execute(text("SELECT nspname FROM pg_namespace"))).scalars())
    assert schemas >= SCHEMAS
    exts = set((await uow.session.execute(text("SELECT extname FROM pg_extension"))).scalars())
    assert {"vector", "pg_trgm", "unaccent", "citext"} <= exts


@pytest.mark.parametrize(
    ("doc", "query"),
    [
        ("São Paulo lesões", "sao paulo lesoes"),
        ("Sao Paulo lesão", "são paulo lesao"),
        ("Grêmio vence o Atlético", "gremio atletico"),
    ],
)
async def test_pt_unaccent_matches_without_accents(uow: UnitOfWork, doc: str, query: str) -> None:
    # Singular/plural ão↔ões не сводятся и в штатном `portuguese` (snowball: lesã / lesõ),
    # поэтому проверяется только независимость от акцентов (BE-T0.3 §18).
    q = text("SELECT to_tsvector('pt_unaccent', :d) @@ plainto_tsquery('pt_unaccent', :q)")
    assert (await uow.session.execute(q, {"d": doc, "q": query})).scalar() is True


async def test_immutable_unaccent(uow: UnitOfWork) -> None:
    q = text("SELECT platform.immutable_unaccent('Grêmio Conceição')")
    assert (await uow.session.execute(q)).scalar() == "Gremio Conceicao"


async def _count(db: Database) -> int:
    async with db.uow() as u:
        return (await u.session.execute(text("SELECT count(*) FROM probe"))).scalar_one()


async def test_uow_rolls_back_and_skips_on_commit(db: Database) -> None:
    async with db.uow() as u:
        await u.session.execute(text("CREATE TABLE probe (id int)"))
    called: list[str] = []

    async def cb() -> None:
        called.append("x")

    async def insert_then_fail() -> None:
        async with db.uow() as u:
            u.on_commit(cb)
            await u.session.execute(text("INSERT INTO probe VALUES (1)"))
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await insert_then_fail()
    assert await _count(db) == 0
    assert called == []


async def test_on_commit_runs_after_commit_and_swallows_errors(db: Database) -> None:
    async with db.uow() as u:
        await u.session.execute(text("CREATE TABLE probe (id int)"))
    seen: list[int] = []

    async def failing() -> None:
        raise ValueError("callback failure must not propagate")

    async def record() -> None:
        seen.append(await _count(db))  # видит закоммиченную строку

    async with db.uow() as u:
        u.on_commit(failing)
        u.on_commit(record)
        await u.session.execute(text("INSERT INTO probe VALUES (1)"))
        assert seen == []
    assert seen == [1]


@pytest.mark.integration_commit
async def test_advisory_xact_lock_blocks_second_connection(pg_container: str) -> None:
    db = Database(pg_container, pool_size=2)
    try:
        acquired = asyncio.Event()

        async def second() -> None:
            async with db.uow() as u:
                await u.advisory_xact_lock("k")
                acquired.set()

        async with db.uow() as first:
            await first.advisory_xact_lock("k")
            task = asyncio.create_task(second())
            await asyncio.sleep(0.3)
            assert not acquired.is_set()
        await asyncio.wait_for(task, 5)
        assert acquired.is_set()
    finally:
        await db.dispose()


@pytest.mark.integration_commit
async def test_readyz_reflects_migrations(pg_container: str, alembic_cfg: Config) -> None:
    settings = Settings(env="ci", database_url=pg_container, app_base_url="http://testserver")

    async def readyz() -> httpx.Response:
        app = create_app(settings)
        transport = httpx.ASGITransport(app=app)
        try:
            async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
                return await c.get("/readyz")
        finally:
            await app.state.db.dispose()

    ok = await readyz()
    assert ok.status_code == 200
    assert ok.json() == {
        "status": "ok",
        "db": "ok",
        "migrations": "ok",
        "revision": head_revision(),
    }

    cfg = alembic_cfg
    await asyncio.to_thread(command.downgrade, cfg, "-1")
    try:
        behind = await readyz()
        assert behind.status_code == 503
        assert behind.json() == {"status": "unavailable", "db": "ok", "migrations": "behind"}
    finally:
        await asyncio.to_thread(command.upgrade, cfg, "head")


async def test_readyz_db_down() -> None:
    settings = Settings(
        env="ci",
        database_url="postgresql+psycopg://u:p@127.0.0.1:1/none",
        app_base_url="http://testserver",
    )
    app = create_app(settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        r = await c.get("/readyz")
    assert r.status_code == 503
    assert r.json()["db"] == "down"
