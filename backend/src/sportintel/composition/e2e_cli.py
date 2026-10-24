"""CLI e2e-окружения (BE-T5.1): сброс данных и принудительный опрос источников. Только ENV=e2e."""

import asyncio
import sys
import uuid

from sqlalchemy import text

from sportintel.composition import tasks as _tasks  # noqa: F401  (регистрация задач для enqueue)
from sportintel.platform import jobs
from sportintel.platform.config import load_settings_or_exit
from sportintel.platform.db import Database
from sportintel.platform.db_metadata import load_all

KEEP_SCHEMAS = {"taxonomy"}  # справочники остаются
KEEP_TABLES = {"platform.app_settings"}
USERS = [
    ("researcher@e2e.test", "researcher"),
    ("editor@e2e.test", "editor"),
    ("admin@e2e.test", "admin"),
]
SOURCES = [("globo", "globo", "A"), ("uol", "uol", "A"), ("espn", "espn", "B")]
FAKE_SOURCE = "http://fake-source:8080"


def guard(env: str) -> None:
    if env != "e2e":
        print(f"refusing to run with ENV={env}: e2e only", file=sys.stderr)
        raise SystemExit(2)


def tables_to_truncate() -> list[str]:
    """По реестру MetaData, а не жёсткому списку — новые таблицы не забываются (§22)."""
    out = []
    for md in load_all():
        for t in (
            md.tables.values()
        ):  # без сортировки: внешние ключи между схемами, порядок решает CASCADE
            full = f"{t.schema}.{t.name}"
            if t.schema not in KEEP_SCHEMAS and full not in KEEP_TABLES:
                out.append(full)
    return sorted(set(out))


async def reset(db: Database) -> None:
    async with db.uow() as uow:
        s = uow.session
        await s.execute(
            text(f"TRUNCATE {', '.join(tables_to_truncate())} RESTART IDENTITY CASCADE")
        )
        await s.execute(text("DELETE FROM procrastinate.procrastinate_jobs"))
        for email, role in USERS:
            await s.execute(
                text(
                    "INSERT INTO identity.users (id, email, display_name, role) VALUES (:i, :e, :n, :r)"
                ),
                {"i": uuid.uuid4(), "e": email, "n": email.split("@")[0], "r": role},
            )
        for slug, group, tier in SOURCES:
            await s.execute(
                text(
                    "INSERT INTO sources.sources (id, name, domain, base_url, kind, feed_urls, tier, owner_group, next_poll_at)"
                    " VALUES (:i, :n, :d, :b, 'rss', ARRAY[:f], :t, :g, now())"
                ),
                {
                    "i": uuid.uuid4(),
                    "n": slug,
                    "d": f"{slug}.e2e.test",
                    "b": f"https://{slug}.e2e.test",
                    "f": f"{FAKE_SOURCE}/{slug}/feed.xml",
                    "t": tier,
                    "g": group,
                },
            )


async def poll(db: Database, database_url: str) -> int:
    async with db.uow() as uow:
        ids = [
            r[0]
            for r in await uow.session.execute(
                text("SELECT id FROM sources.sources WHERE active AND kind <> 'manual'")
            )
        ]
    await jobs.open(database_url)
    try:
        for i in ids:
            await jobs.enqueue(
                "ingestion.fetch_source", queueing_lock=f"fetch:{i}", source_id=str(i)
            )
    finally:
        await jobs.close()
    return len(ids)


def _main(action: str) -> None:
    settings = load_settings_or_exit()
    guard(settings.env)

    async def go() -> None:
        db = Database(settings.database_url, 2)
        try:
            if action == "reset":
                await reset(db)
            else:
                print(f"enqueued {await poll(db, settings.database_url)} sources")
        finally:
            await db.dispose()

    asyncio.run(go())


def reset_cli() -> None:
    _main("reset")


def poll_cli() -> None:
    _main("poll")
