from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sportintel.modules.editorial.infrastructure.tables import translations as t


class SqlTranslationCache:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, key: str) -> str | None:
        return (await self.session.execute(select(t.c.text).where(t.c.key == key))).scalar()

    async def put(self, key: str, lang: str, text: str, model: str) -> None:
        await self.session.execute(
            pg_insert(t)
            .values(key=key, lang=lang, text=text, model=model)
            .on_conflict_do_nothing(index_elements=[t.c.key])
        )
