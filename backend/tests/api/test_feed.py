from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from tests.api.conftest import dev_login
from tests.factories import make_article, make_event, make_source

from sportintel.modules.editorial.api.channels_router import ChannelIn
from sportintel.modules.editorial.application import autodraft
from sportintel.modules.editorial.jobs import channels_repo, repo_for
from sportintel.modules.events.domain.values import (
    ArticleLink,
    AssessmentOrigin,
    AttachMethod,
    EventStatus,
    Relevance,
    RelevanceAssessment,
)
from sportintel.modules.events.jobs import repo_for as event_repo
from sportintel.modules.sources.domain.values import SourceTier
from sportintel.platform import ai_usage
from sportintel.platform.clock import FrozenClock
from sportintel.platform.db import Database

pytestmark = pytest.mark.integration
IN_FIELDS = set(ChannelIn.model_fields)
CLOCK = FrozenClock(datetime(2026, 10, 9, 12, tzinfo=UTC))


def rel(level: str) -> RelevanceAssessment:
    return RelevanceAssessment(Relevance(level), "r", AssessmentOrigin.RULE)


async def test_autodraft_feed_and_take(make_app, client_for, db: Database) -> None:  # type: ignore[no-untyped-def]
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A)
        hot = await make_event(
            u,
            [
                await make_article(
                    u, s, title="Flamengo demite técnico", lead="Clube anunciou a saída."
                )
            ],
            relevance=rel("HIGH"),
            sport_id="football",
            now=CLOCK.now(),
        )
        low = await make_event(u, [await make_article(u, s)], relevance=rel("LOW"), now=CLOCK.now())
        ready = await make_event(
            u,
            [await make_article(u, s)],
            relevance=rel("HIGH"),
            status=EventStatus.READY,
            now=CLOCK.now(),
        )

    rep = await autodraft.run(db, repo_for, CLOCK)
    assert rep.created == 1
    assert rep.failed == 0
    assert (await autodraft.run(db, repo_for, CLOCK)).created == 0  # повтор — basis_hash тот же
    async with db.uow() as u:
        st = (
            await u.session.execute(
                text("SELECT status, draft_state FROM events.events WHERE id=:i"), {"i": hot.id}
            )
        ).one()
        assert tuple(st) == ("NEW", "ready")  # авто-черновик статус не меняет
        a2 = await make_article(u, s, title="Outra fonte")
        e = await event_repo(u).get(hot.id)
        assert e
        e.attach(ArticleLink(a2.id, CLOCK.now(), 0.9, AttachMethod.AUTO), CLOCK.now())
        await event_repo(u).save(e, e.version)
    assert (await autodraft.run(db, repo_for, CLOCK)).rebuilt == 1

    app = make_app()
    app.state.clock = CLOCK  # the feed window counts from the app clock, not the wall clock
    c = client_for(app)
    me = await dev_login(c, "feed@corp.com", "editor")
    h = {"X-CSRF-Token": me["csrf_token"]}
    feed = (await c.get("/api/v1/feed")).json()
    ids = [i["event"]["id"] for i in feed["items"]]
    assert str(hot.id) in ids
    assert str(low.id) not in ids
    item = next(i for i in feed["items"] if i["event"]["id"] == str(hot.id))
    assert (item["draft"]["version_n"], item["draft"]["origin"]) == (2, "template")
    assert item["draft"]["body_tg_html"].startswith("<b>⚽ Flamengo demite técnico</b>")
    assert item["sources"][0]["url"].startswith("https://")
    channel = [
        i["event"]["id"]
        for i in (await c.get("/api/v1/feed", params={"tab": "channel"})).json()["items"]
    ]
    assert channel == [str(ready.id)]

    version = item["event"]["version"]
    r = await c.post(f"/api/v1/feed/{hot.id}:take", headers={**h, "If-Match": f'"{version}"'})
    assert r.status_code == 200, r.text
    assert (r.json()["event"]["status"], r.json()["draft_id"]) == ("DRAFT", item["draft"]["id"])
    again = await c.post(f"/api/v1/feed/{hot.id}:take", headers={**h, "If-Match": f'"{version}"'})
    assert again.status_code == 409
    assert (await c.post(f"/api/v1/feed/{hot.id}:take", headers=h)).status_code == 428
    # взятое в работу остаётся в ленте до планирования
    after = (await c.get("/api/v1/feed")).json()["items"]
    assert [i["event"]["status"] for i in after if i["event"]["id"] == str(hot.id)] == ["DRAFT"]


async def test_feed_prepares_a_post_and_schedules_it_in_one_step(  # type: ignore[no-untyped-def]
    make_app, client_for, db: Database, monkeypatch
) -> None:
    """«Подготовить» → «Запланировать» = «Готово» + закрепление в канале. В «Ленте» —
    только посты на языке канала: без поста или с постом на другом языке события там нет."""
    app = make_app()
    now = app.state.clock.now()
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A, language="en")
        ev = await make_event(
            u,
            [await make_article(u, s, title="Pedro is out", lead="Injury confirmed.")],
            relevance=rel("HIGH"),
            sport_id="football",
            now=now,
        )
        await u.session.execute(
            text('UPDATE events.events SET title_i18n = \'{"ru": "Педро выбыл"}\' WHERE id=:i'),
            {"i": ev.id},
        )
    admin, editor = client_for(app), client_for(app)
    ha = {"X-CSRF-Token": (await dev_login(admin, "fa@corp.com", "admin"))["csrf_token"]}
    he = {"X-CSRF-Token": (await dev_login(editor, "fe@corp.com", "editor"))["csrf_token"]}
    ch = (
        await admin.post(
            "/api/v1/channels",
            json={"name": "Main", "tg_chat_id": "-1001234567890", "language": "ru"},
            headers=ha,
        )
    ).json()

    feed = (await editor.get("/api/v1/feed")).json()
    assert feed["items"] == []  # поста ещё нет
    assert [c["name"] for c in feed["channels"]] == ["Main"]
    version = (await editor.get(f"/api/v1/events/{ev.id}")).json()["version"]

    def ver(e: str) -> dict[str, str]:
        return {**he, "If-Match": f'"{e}"'}

    r = await editor.post(
        f"/api/v1/feed/{ev.id}:prepare",
        json={"mode": "template"},
        headers=ver(version),
    )
    assert r.status_code == 204, r.text
    # шаблон на языке статьи (en), канал ru — в «Ленте» его нет
    assert (await editor.get("/api/v1/feed")).json()["items"] == []
    version = (await editor.get(f"/api/v1/events/{ev.id}")).json()["version"]
    at = (now + timedelta(hours=2)).isoformat()
    body = {"channel_id": ch["id"], "publish_at": at}
    # и запланировать его нельзя: отказ, событие остаётся черновиком
    r = await editor.post(f"/api/v1/feed/{ev.id}:schedule", json=body, headers=ver(version))
    assert r.status_code == 422
    assert "language" in r.text
    assert (await editor.get(f"/api/v1/events/{ev.id}")).json()["status"] == "DRAFT"

    upd = await admin.put(
        f"/api/v1/channels/{ch['id']}",
        json={k: v for k, v in {**ch, "language": "en"}.items() if k in IN_FIELDS},
        headers={**ha, "If-Match": f'"{ch["version"]}"'},
    )
    assert upd.status_code == 200, upd.text
    item = (await editor.get("/api/v1/feed")).json()["items"][0]
    assert (item["title"], item["draft"]["lang"], item["event"]["status"]) == (
        "Педро выбыл",
        "en",
        "DRAFT",
    )
    r = await editor.post(f"/api/v1/feed/{ev.id}:schedule", json=body, headers=ver(version))
    assert r.status_code == 204, r.text
    assert (await editor.get(f"/api/v1/events/{ev.id}")).json()["status"] == "READY"
    sched = (await admin.get(f"/api/v1/channels/{ch['id']}/schedule")).json()
    assert [(p["event_id"], p["pinned"]) for p in sched["posts"]] == [(str(ev.id), True)]


class FakeLlm:
    model = "fake"

    async def complete_json(self, system: str, user: str, schema: type) -> object:
        return schema.model_validate(
            {"headline": "Flamengo fires coach", "body": "As [ge reported](1), the club decided."}
        )


async def test_first_version_is_written_by_ai_and_approved_as_is(  # type: ignore[no-untyped-def]
    make_app, client_for, db: Database
) -> None:
    """Исходный замысел: первый вариант поста уже хороший — ИИ пишет его сам, редактор
    одобряет его одной кнопкой прямо у нового события, без перегенерации."""
    app = make_app()
    now = app.state.clock.now()
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A)
        ev = await make_event(
            u,
            [await make_article(u, s, title="Flamengo demite técnico", lead="Saída anunciada.")],
            relevance=rel("HIGH"),
            sport_id="football",
            now=now,
        )
        await u.session.execute(
            text("UPDATE events.events SET source_ids = ARRAY[CAST(:s AS uuid)] WHERE id=:i"),
            {"s": s.id, "i": ev.id},
        )
    admin, editor = client_for(app), client_for(app)
    ha = {"X-CSRF-Token": (await dev_login(admin, "aa@corp.com", "admin"))["csrf_token"]}
    he = {"X-CSRF-Token": (await dev_login(editor, "ae@corp.com", "editor"))["csrf_token"]}
    ch = (
        await admin.post(
            "/api/v1/channels",
            json={"name": "Main", "tg_chat_id": "-1001234567890", "language": "en"},
            headers=ha,
        )
    ).json()
    clock = app.state.clock
    assert (await autodraft.run(db, repo_for, clock)).created == 1  # шаблон — сразу
    assert await autodraft.ai_first_version(db, repo_for, channels_repo, clock, FakeLlm())
    assert not await autodraft.ai_first_version(db, repo_for, channels_repo, clock, FakeLlm())

    item = next(
        i
        for i in (await editor.get("/api/v1/feed")).json()["items"]
        if i["event"]["id"] == str(ev.id)
    )
    assert (item["event"]["status"], item["draft"]["origin"], item["draft"]["lang"]) == (
        "NEW",
        "ai",
        "en",
    )
    assert '<a href="' in item["draft"]["body_tg_html"]  # ссылка на источник прямо в тексте
    # фильтры — те же, что у списка событий: исключённый источник прячет событие
    for q in ({"source_exclude": str(s.id)}, {"sport": "tennis"}, {"region": "RU"}):
        assert (await editor.get("/api/v1/feed", params=q)).json()["items"] == [], q
    assert (
        len((await editor.get("/api/v1/feed", params={"source": str(s.id)})).json()["items"]) == 1
    )

    r = await editor.post(
        f"/api/v1/feed/{ev.id}:approve",
        headers={**he, "If-Match": f'"{item["event"]["version"]}"'},
    )
    assert r.status_code == 204, r.text
    assert (await editor.get(f"/api/v1/events/{ev.id}")).json()["status"] == "READY"
    sched = (await admin.get(f"/api/v1/channels/{ch['id']}/schedule")).json()
    assert [q["body_tg_html"] for q in sched["queue"]] == [item["draft"]["body_tg_html"]]


async def test_ai_progress_shows_what_is_written_now_and_the_queue(  # type: ignore[no-untyped-def]
    make_app, client_for, db: Database
) -> None:
    """Прогресс: какое событие ИИ пишет сейчас, сколько в очереди и сколько ждать;
    аналитика — справляется ли ИИ с потоком."""
    app = make_app()
    now = app.state.clock.now()
    async with db.uow() as u:
        s = await make_source(u, tier=SourceTier.A)
        evs = [
            await make_event(
                u, [await make_article(u, s, title=f"Notícia {i}")], relevance=rel("HIGH"), now=now
            )
            for i in range(3)
        ]
    clock = app.state.clock
    assert (await autodraft.run(db, repo_for, clock)).created == 3
    admin = client_for(app)
    await dev_login(admin, "ai@corp.com", "admin")

    p = (await admin.get("/api/v1/ai/progress")).json()
    post = next(q for q in p["queues"] if q["kind"] == "post")
    assert post["pending"] == 3
    assert post["eta_s"] == 3 * 60  # модель ещё не мерили: ~50 с → пост в минуту
    assert len(post["next"]) == 3
    assert p["running"] == []

    async with ai_usage.track(db, "post", "fake", evs[0].id):
        p = (await admin.get("/api/v1/ai/progress")).json()
        (run,) = p["running"]
        assert (run["kind"], run["event_id"], run["typical_s"]) == ("post", str(evs[0].id), 50)
        assert run["title"].startswith("Notícia")
        post = next(q for q in p["queues"] if q["kind"] == "post")
        assert str(evs[0].id) not in [i["event_id"] for i in post["next"]]  # он уже «сейчас»

    assert await autodraft.ai_first_version(db, repo_for, channels_repo, clock, FakeLlm())
    p = (await admin.get("/api/v1/ai/progress")).json()
    post = next(q for q in p["queues"] if q["kind"] == "post")
    assert post["pending"] == 2
    assert post["done_24h"] >= 1  # считаются события, а не вызовы

    load = (await admin.get("/api/v1/analytics/ai-load")).json()
    assert load["backlog"]["post"] == 2
    assert {k["kind"] for k in load["kinds"]} == {"post"}
    assert load["verdict"] in {"ok", "off"}
