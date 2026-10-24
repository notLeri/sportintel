import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from sportintel.platform.db_metadata import load_all

config = context.config
if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = load_all()


def _url() -> str:
    # Тесты передают URL явно; иначе — роль migrator из env (CONV §2).
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    from sportintel.platform.config import get_settings

    settings = get_settings()
    return settings.database_url_migrator or settings.database_url


def _configure(connection: object | None = None, **kw: object) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_schemas=True,
        compare_type=True,
        **kw,
    )


def run_offline() -> None:
    _configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def _run_sync(connection: object) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_online() -> None:
    engine = create_async_engine(_url())
    async with engine.connect() as conn:
        await conn.run_sync(_run_sync)
    await engine.dispose()


if context.is_offline_mode():
    run_offline()
else:
    asyncio.run(run_online())
