"""Периодическая проверка тихих отказов (BE-T4.13)."""

import json
from datetime import timedelta
from typing import Any

from sqlalchemy import text

from sportintel.composition.health_rules import HealthInputs, SourceHealth, evaluate, plan
from sportintel.modules.ingestion import public as ingestion
from sportintel.modules.sources import public as sources
from sportintel.platform import jobs, settings_store
from sportintel.platform.clock import Clock
from sportintel.platform.config import get_settings
from sportintel.platform.db import Database
from sportintel.platform.notify import TelegramNotifier


async def run(db: Database, clock: Clock, notifier: Any) -> list[tuple[str, str, bool]]:
    cfg: Any = await settings_store.get(db, "health_watch")
    langs: Any = await settings_store.get(db, "languages")
    now = clock.now()
    async with db.uow() as uow:
        queues = await jobs.queue_stats(uow.session)
        lag = await ingestion.ingest_lag_p95(uow, now - timedelta(minutes=30))
        srcs = [
            SourceHealth(**r)
            for r in await sources.list_health_inputs(uow, now - timedelta(days=7))
        ]
        state = {
            r.alert_key: dict(r._mapping)
            for r in await uow.session.execute(text("SELECT * FROM platform.alert_state"))
        }
    firing = evaluate(
        HealthInputs({q.queue: q.oldest_todo_age_s for q in queues}, lag, srcs),
        now,
        cfg,
        langs.ui_language,
    )
    texts = {f.alert_key: f.text for f in firing}
    msgs = plan(firing, state, now, cfg.repeat_minutes, langs.ui_language)
    for key, msg, is_firing in msgs:
        await notifier.send(msg)
        async with db.uow() as uow:
            await uow.session.execute(
                text(
                    "INSERT INTO platform.alert_state (alert_key, firing, last_sent_at, details) VALUES (:k, :f, :t, CAST(:d AS jsonb))"
                    " ON CONFLICT (alert_key) DO UPDATE SET firing = excluded.firing, last_sent_at = excluded.last_sent_at,"
                    " details = coalesce(excluded.details, platform.alert_state.details)"
                ),
                {
                    "k": key,
                    "f": is_firing,
                    "t": now,
                    "d": json.dumps({"text": texts[key]}) if key in texts else None,
                },
            )
    return msgs


@jobs.periodic(
    "platform.health_watch", cron="*/5 * * * *", queue="maintenance", lock="health_watch"
)
async def health_watch(timestamp: int) -> None:
    rt = jobs.runtime()
    s = get_settings()
    token = s.alert_telegram_bot_token.get_secret_value() if s.alert_telegram_bot_token else None
    await run(rt.db, rt.clock, TelegramNotifier(token, s.alert_telegram_chat_id))
