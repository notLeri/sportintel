"""Публикация в канал: approval-режим, без повторов, ошибка Telegram пишется в журнал."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from tests.factories import make_article, make_event, make_source

from sportintel.modules.editorial.application import publishing
from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository
from sportintel.modules.editorial.infrastructure.channels_repository import SqlChannelRepository
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.modules.events.domain.values import EventStatus
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.ids import new_id
from sportintel.platform.notify import PublishError

NOW = datetime(2026, 10, 9, 18, tzinfo=UTC)


class FakeTelegram:
    def __init__(self, fail: str | None = None) -> None:
        self.sent: list[tuple[str, str]] = []
        self.fail = fail

    async def send(self, chat_id: str, html: str) -> int:
        if self.fail:
            raise PublishError(self.fail)
        self.sent.append((chat_id, html))
        return len(self.sent)


async def setup(db: Database) -> tuple[publishing.Channel, object]:
    async with db.uow() as u:
        s = await make_source(u, domain=f"pub-{new_id()}.example.com", tier=SourceTier.A)
        a = await make_article(u, s, title="Pedro é cortado")
        ev = await make_event(
            u, [a], status=EventStatus.READY, sport_id="football", now=NOW, relevance_rank=3
        )
        await u.session.execute(
            text("UPDATE events.events SET relevance = 'HIGH' WHERE id = :i"), {"i": ev.id}
        )
        drafts = SqlDraftRepository(u.session)
        draft_id = new_id()
        await drafts.create(draft_id, ev.id, "ready", None, NOW)
        await drafts.add_version(
            draft_id,
            1,
            {
                "body_tg_html": "<b>Педро выбыл</b>",
                "origin": "human",
                "lang": "ru",
                "disclaimer_kinds": ["unconfirmed"],
            },
            NOW,
        )
        await drafts.update(draft_id, NOW, current_version=1)
        cid = new_id()
        values = {
            "id": cid, "name": "Test", "tg_chat_id": "-100123", "language": "ru",
            "mode": "approval", "cron": "0 * * * *", "format": "single", "max_per_run": 5,
            "min_relevance": "HIGH", "min_trust": "MEDIUM",
        }  # fmt: skip
        await SqlChannelRepository(u.session).create(values, NOW)
        row = await SqlChannelRepository(u.session).get(cid)
    return publishing.channel_of(row), ev  # type: ignore[arg-type]


def repos() -> tuple[object, object, object]:
    return (
        lambda u: SqlChannelRepository(u.session),
        lambda u: SqlDraftRepository(u.session),
        lambda u: SqlBriefRepository(u.session),
    )


async def test_approval_post_is_sent_once_and_event_published(db: Database) -> None:
    ch, ev = await setup(db)
    tg = FakeTelegram()
    r = await publishing.run_channel(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert (r.sent, r.failed) == (1, 0)
    assert tg.sent[0][0] == "-100123"
    assert tg.sent[0][1] == "<b>Педро выбыл</b>"  # дисклеймер — редактору, не в канал
    async with db.uow() as u:
        status = (
            await u.session.execute(
                text("SELECT status FROM events.events WHERE id = :i"),
                {"i": ev.id},  # type: ignore[attr-defined]
            )
        ).scalar()
    assert status == "PUBLISHED"
    again = await publishing.run_channel(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert again.sent == 0
    assert len(tg.sent) == 1


async def test_telegram_error_is_logged_not_retried_forever(db: Database) -> None:
    ch, _ = await setup(db)
    r = await publishing.run_channel(
        db,
        ch,
        FrozenClock(NOW),
        FakeTelegram(fail="chat not found"),
        *repos(),  # type: ignore[arg-type]
    )
    assert r.failed == 1
    async with db.uow() as u:
        pubs = await SqlChannelRepository(u.session).publications(ch.id)
    assert (pubs[0]["status"], pubs[0]["error"]) == ("failed", "chat not found")


async def test_plan_shows_next_post_without_sending(db: Database) -> None:
    ch, ev = await setup(db)
    posts, _, skipped = await publishing.plan_posts(db, ch, NOW, *repos(), limit=5)  # type: ignore[arg-type]
    assert [p.event_id for p in posts] == [ev.id]
    assert posts[0].body == "<b>Педро выбыл</b>"
    assert not skipped
    async with db.uow() as u:  # ничего не отправлено и не записано
        assert await SqlChannelRepository(u.session).publications(ch.id) == []


async def test_pinned_post_waits_for_its_time_not_cron(db: Database) -> None:
    ch, ev = await setup(db)
    at = NOW + timedelta(hours=5)
    async with db.uow() as u:
        await SqlChannelRepository(u.session).pin(ch.id, ev.id, at, None)  # type: ignore[attr-defined]
    tg = FakeTelegram()
    r = await publishing.run_channel(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert (r.sent, tg.sent) == (0, [])  # очередной запуск cron закреплённый пост не берёт
    early = await publishing.run_pinned(
        db, ch, FrozenClock(at - timedelta(minutes=1)), tg, *repos()
    )  # type: ignore[arg-type]
    assert early.sent == 0
    r = await publishing.run_pinned(db, ch, FrozenClock(at), tg, *repos())  # type: ignore[arg-type]
    assert (r.sent, tg.sent[0][1]) == (1, "<b>Педро выбыл</b>")
    async with db.uow() as u:
        assert await SqlChannelRepository(u.session).pins(ch.id) == {}


async def test_missed_pin_is_not_sent_late(db: Database) -> None:
    """Автопостинг был выключен, время прошло: пост не уходит сам — ждёт нового времени."""
    ch, ev = await setup(db)
    async with db.uow() as u:
        await SqlChannelRepository(u.session).pin(ch.id, ev.id, NOW - timedelta(hours=1), None)  # type: ignore[attr-defined]
    tg = FakeTelegram()
    r = await publishing.run_pinned(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert (r.sent, tg.sent) == (0, [])
    async with db.uow() as u:
        assert ev.id in await SqlChannelRepository(u.session).pins(ch.id)  # type: ignore[attr-defined]


async def test_only_the_approved_current_version_is_sent(db: Database) -> None:
    """Регрессия: в канал ушла старая шаблонная версия на языке канала, а редактор утвердил
    другую (текущую). Отправляется только текущая версия и только на языке канала."""
    ch, ev = await setup(db)  # v1 «Педро выбыл» на ru — текущая
    async with db.uow() as u:
        drafts = SqlDraftRepository(u.session)
        draft = await drafts.by_event(ev.id)  # type: ignore[attr-defined]
        await drafts.add_version(
            draft["id"], 2, {"body_tg_html": "<b>Pedro out</b>", "origin": "ai", "lang": "en"}, NOW
        )
        await drafts.update(draft["id"], NOW, current_version=2)
    tg = FakeTelegram()
    r = await publishing.run_channel(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert (r.sent, r.skipped, tg.sent) == (0, 1, [])  # канал ru, утверждена en — не отправлять

    async with db.uow() as u:
        drafts = SqlDraftRepository(u.session)
        await drafts.add_version(
            draft["id"], 3, {"body_tg_html": "<b>Педро — новая версия</b>", "origin": "human",
                             "lang": "ru"}, NOW,
        )  # fmt: skip
        await drafts.update(draft["id"], NOW, current_version=3)
    r = await publishing.run_channel(db, ch, FrozenClock(NOW), tg, *repos())  # type: ignore[arg-type]
    assert tg.sent[0][1] == "<b>Педро — новая версия</b>"  # не v1 и не «последняя на ru»
