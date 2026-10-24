"""Фабрики валидных сущностей для тестов (CONV §13). Сырые INSERT в тестах запрещены."""

import itertools
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from sportintel.modules.events.domain.event import Event
from sportintel.modules.events.domain.values import ArticleLink, AttachMethod, TextOrigin
from sportintel.modules.events.infrastructure.repository import SqlEventRepository
from sportintel.modules.identity.domain.user import User
from sportintel.modules.identity.domain.values import Locale, Role
from sportintel.modules.identity.infrastructure.repository import SqlUserRepository
from sportintel.modules.ingestion.domain.article import Article, NewArticle
from sportintel.modules.ingestion.infrastructure.repository import SqlArticleRepository
from sportintel.modules.sources.domain.source import Source
from sportintel.modules.sources.domain.values import SourceKind, SourceTier
from sportintel.modules.sources.infrastructure.repository import SqlSourceRepository
from sportintel.modules.taxonomy.domain.entity import Entity
from sportintel.modules.taxonomy.domain.values import EntityKind
from sportintel.modules.taxonomy.infrastructure.repository import SqlTaxonomyRepository
from sportintel.platform.db import UnitOfWork
from sportintel.platform.ids import new_id
from sportintel.platform.text import normalize_name

_seq = itertools.count(1)


async def make_user(uow: UnitOfWork, **overrides: Any) -> User:
    n = next(_seq)
    user = User(
        id=new_id(),
        email=f"user{n}@example.com",
        display_name=f"User {n}",
        role=Role.RESEARCHER,
        locale=Locale.PT_BR,
        timezone="America/Sao_Paulo",
        hotkeys_enabled=True,
        active=True,
        invited=False,
        oidc_subject=None,
        last_login_at=None,
        version=1,
    )
    user = replace(user, **overrides)
    await SqlUserRepository(uow.session).insert(user)
    return user


async def make_source(uow: UnitOfWork, **overrides: Any) -> Source:
    n = next(_seq)
    domain = overrides.pop("domain", f"news{n}.example.com")
    source = Source(
        id=new_id(),
        name=f"Source {n}",
        domain=domain,
        base_url=f"https://{domain}",
        kind=SourceKind.RSS,
        feed_urls=[f"https://{domain}/feed.xml"],
        tier=SourceTier.B,
        owner_group=f"group{n}",
    )
    source = replace(source, **overrides)
    source.validate(frozenset({"default", "cbf"}))
    await SqlSourceRepository(uow.session).add(source)
    return source


async def make_article(uow: UnitOfWork, source: Source, **overrides: Any) -> Article:
    n = next(_seq)
    url = overrides.pop("url", f"https://{source.domain}/noticia/{n}")
    now = overrides.pop("now", datetime(2026, 10, 7, 12, tzinfo=UTC))
    item = NewArticle(
        source_id=source.id,
        canonical_url=url,
        original_url=url,
        title=overrides.pop("title", f"Notícia {n}"),
        lead=overrides.pop("lead", None),
        published_at=overrides.pop("published_at", None),
        image_url=None,
        author=None,
        **overrides,
    )
    repo = SqlArticleRepository(uow.session)
    (article_id,) = await repo.insert_new([item], now)
    article = await repo.get(article_id)
    assert article is not None
    return article


async def make_entity(uow: UnitOfWork, name: str | None = None, **overrides: Any) -> Entity:
    n = next(_seq)
    name = name or f"Entidade {n}"
    entity = Entity(
        id=new_id(),
        kind=overrides.pop("kind", EntityKind.TEAM),
        sport_id=overrides.pop("sport_id", "football"),
        canonical_name=name,
        name_norm=normalize_name(name),
        **overrides,
    )
    return await SqlTaxonomyRepository(uow.session).add_entity(entity)


async def make_event(uow: UnitOfWork, articles: list[Article], **overrides: Any) -> Event:
    now = overrides.pop("now", datetime(2026, 10, 7, 12, tzinfo=UTC))
    first, *rest = articles
    e = Event.create_auto(
        new_id(),
        ArticleLink(first.id, now, None, AttachMethod.NEW),
        overrides.pop("title", first.title),
        TextOrigin.SOURCE,
        now,
        now,
    )
    for a in rest:
        e.attach(ArticleLink(a.id, now, 0.9, AttachMethod.AUTO), now)
    for k, v in overrides.items():
        setattr(e, k, v)
    await SqlEventRepository(uow.session).add(e)
    return e
