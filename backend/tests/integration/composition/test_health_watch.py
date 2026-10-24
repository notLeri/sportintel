from datetime import UTC, datetime, timedelta

import httpx
import respx
from sqlalchemy import text
from tests.factories import make_source

from sportintel.composition import health_watch
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform import settings_store
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database
from sportintel.platform.notify import TelegramNotifier

DAY = datetime(2026, 10, 9, 15, tzinfo=UTC)


class Collect:
    def __init__(self) -> None:
        self.sent: list[str] = []

    async def send(self, text: str) -> None:
        self.sent.append(text)


async def test_firing_repeat_and_resolve(db: Database) -> None:
    settings_store.clear_cache()
    async with db.uow() as u:
        await u.session.execute(text("DELETE FROM platform.alert_state"))
        s = await make_source(u, name="Fonte Silenciosa", tier=SourceTier.A)
        await u.session.execute(
            text("UPDATE sources.sources SET last_new_article_at = :t WHERE id = :i"),
            {"t": DAY - timedelta(hours=8), "i": s.id},
        )
    n = Collect()
    await health_watch.run(db, FrozenClock(DAY), n)
    assert [m for m in n.sent if "Fonte Silenciosa" in m] == [
        "🔴 Источник <b>Fonte Silenciosa</b> без новых статей уже 8 ч"
    ]
    n.sent.clear()
    await health_watch.run(db, FrozenClock(DAY + timedelta(minutes=5)), n)
    assert not [m for m in n.sent if "Silenciosa" in m]
    async with db.uow() as u:
        await u.session.execute(
            text("UPDATE sources.sources SET last_new_article_at = :t WHERE id = :i"),
            {"t": DAY, "i": s.id},
        )
    await health_watch.run(db, FrozenClock(DAY + timedelta(minutes=10)), n)
    assert [m for m in n.sent if "Silenciosa" in m] == [
        "✅ Исправлено: Источник <b>Fonte Silenciosa</b> без новых статей уже 8 ч"
    ]


@respx.mock
async def test_telegram_notifier() -> None:
    route = respx.post("https://api.telegram.org/botTOKEN/sendMessage").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await TelegramNotifier("TOKEN", "-100").send("🔴 x")
    assert route.called
    import json

    assert json.loads(route.calls[0].request.content) == {
        "chat_id": "-100",
        "text": "🔴 x",
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
