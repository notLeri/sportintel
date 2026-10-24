"""Фоновые задачи модуля editorial (CONV §10)."""

import time
import uuid

from sportintel.modules.editorial.application import autodraft, briefs, publishing, translate
from sportintel.modules.editorial.infrastructure.briefs_repository import SqlBriefRepository
from sportintel.modules.editorial.infrastructure.channels_repository import SqlChannelRepository
from sportintel.modules.editorial.infrastructure.repository import SqlDraftRepository
from sportintel.modules.editorial.infrastructure.translations_repository import SqlTranslationCache
from sportintel.platform import flags, jobs
from sportintel.platform.config import get_settings
from sportintel.platform.db import UnitOfWork
from sportintel.platform.notify import TelegramPublisher


def repo_for(uow: UnitOfWork) -> SqlDraftRepository:
    return SqlDraftRepository(uow.session)


def briefs_repo(uow: UnitOfWork) -> SqlBriefRepository:
    return SqlBriefRepository(uow.session)


@jobs.periodic("editorial.autodraft_due", cron="* * * * *", queue="scheduler", lock="autodraft_due")
async def autodraft_due(timestamp: int) -> None:
    rt = jobs.runtime()
    await autodraft.run(rt.db, repo_for, rt.clock)


@jobs.periodic(
    "editorial.ai_first_version_due", cron="* * * * *", queue="ai", lock="ai_first_version_due"
)
async def ai_first_version_due(timestamp: int) -> None:
    """Первый вариант поста пишет ИИ (drafts.auto_mode=llm). Быстрая модель успевает несколько
    постов за запуск: новый начинается, пока с начала запуска прошло меньше AI_BUDGET_S."""
    rt = jobs.runtime()
    llm = await briefs.provider_for(rt.db, get_settings())
    if llm is None:
        return  # модель не подключена — остаётся шаблон
    t0 = time.monotonic()
    while await autodraft.ai_first_version(rt.db, repo_for, channels_repo, rt.clock, llm):
        if time.monotonic() - t0 >= autodraft.AI_BUDGET_S:
            break


@jobs.task("editorial.build_brief", queue="ai", retry=jobs.RetryPolicy(2, 60))
async def build_brief(event_id: str, lang: str) -> None:
    rt = jobs.runtime()
    llm = await briefs.provider_for(rt.db, get_settings())
    if llm is None:
        return  # AI_PROVIDER=none: брифов нет, UI показывает оригинал
    await briefs.build(rt.db, briefs_repo, uuid.UUID(event_id), lang, rt.clock, llm)


@jobs.periodic("editorial.brief_due", cron="*/2 * * * *", queue="scheduler", lock="brief_due")
async def brief_due(timestamp: int) -> None:
    rt = jobs.runtime()
    if await briefs.provider_for(rt.db, get_settings()) is None:
        return
    await briefs.enqueue_due(rt.db, briefs_repo, rt.clock)


def channels_repo(uow: UnitOfWork) -> SqlChannelRepository:
    return SqlChannelRepository(uow.session)


@jobs.periodic("editorial.publish_due", cron="* * * * *", queue="scheduler", lock="publish_due")
async def publish_due(timestamp: int) -> None:
    """Каналы по расписанию. Без FLAG_TELEGRAM_PUBLISH и токена бота — ничего не отправляется."""
    s = get_settings()
    if not flags.is_enabled("TELEGRAM_PUBLISH") or s.telegram_bot_token is None:
        return
    rt = jobs.runtime()
    publisher = TelegramPublisher(s.telegram_bot_token.get_secret_value())
    await publishing.run_due(rt.db, rt.clock, publisher, channels_repo, repo_for, briefs_repo)


def translations_cache(uow: UnitOfWork) -> SqlTranslationCache:
    return SqlTranslationCache(uow.session)


@jobs.periodic("editorial.translate_due", cron="* * * * *", queue="scheduler", lock="translate_due")
async def translate_due(timestamp: int) -> None:
    rt = jobs.runtime()
    if await translate.translator_for(rt.db, get_settings()) is None:
        return  # без ИИ переводов нет: UI показывает оригинал
    await translate.enqueue_due(rt.db, rt.clock)


@jobs.task("editorial.translate_event", queue="translate", retry=jobs.RetryPolicy(2, 60))
async def translate_event(event_id: str, lang: str, full: bool = True) -> None:
    rt = jobs.runtime()
    llm = await translate.translator_for(rt.db, get_settings())
    if llm is None:
        return
    await translate.translate_event(
        rt.db, translations_cache, llm, uuid.UUID(event_id), lang, rt.clock, full
    )
