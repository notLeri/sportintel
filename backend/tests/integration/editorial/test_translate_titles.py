from datetime import UTC, datetime

import pytest
from sqlalchemy import text
from tests.factories import make_article, make_event, make_source

from sportintel.modules.editorial.application import translate
from sportintel.modules.events.domain.values import (
    AssessmentOrigin,
    Relevance,
    RelevanceAssessment,
)
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.llm import FakeProvider

pytestmark = pytest.mark.integration
CLOCK = FrozenClock(datetime(2026, 10, 11, 12, tzinfo=UTC))


class _Cache:
    async def get(self, key: str) -> str | None:
        return None

    async def put(self, key: str, lang: str, text: str, model: str) -> None:
        return None


async def test_low_importance_gets_its_headline_translated_but_not_the_summary(
    db: Database,
) -> None:
    """Низкая важность: заголовок — на языке интерфейса (португальского в списках нет),
    сводка не переводится — это лишние вызовы ИИ."""
    async with db.uow() as u:
        s = await make_source(u)
        art = await make_article(u, s, title="Clube anuncia camisa nova", lead="Lançamento hoje.")
        ev = await make_event(
            u,
            [art],
            relevance=RelevanceAssessment(Relevance.LOW, "r", AssessmentOrigin.RULE),
            now=CLOCK.now(),
        )
    row = next(r for r in await translate.backlog(db, CLOCK) if r["id"] == ev.id)
    assert row["full"] is False  # ниже translate_min_relevance (MEDIUM)

    llm = FakeProvider({"EventText": {"title": "Клуб представил новую форму", "summary": "x"}})
    assert await translate.translate_event(
        db, lambda _: _Cache(), llm, ev.id, "ru", CLOCK, full=False
    )
    async with db.uow() as u:
        title, summary = (
            await u.session.execute(
                text("SELECT title_i18n->>'ru', summary_i18n->'ru' FROM events.events WHERE id=:i"),
                {"i": ev.id},
            )
        ).one()
    assert title == "Клуб представил новую форму"
    assert summary is None
    assert all('"summary":""' in user for _, user in llm.calls)  # лиды модели не отправлялись
