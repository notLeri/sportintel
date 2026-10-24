import uuid
from datetime import UTC, datetime

from sportintel.modules.editorial.domain.channels import (
    Candidate,
    Channel,
    DigestItem,
    is_due,
    matches,
    next_runs,
    render_digest,
)

GE, BLOG = uuid.uuid4(), uuid.uuid4()
NOW = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)


def ch(**kw: object) -> Channel:
    base: dict[str, object] = dict(
        id=uuid.uuid4(), name="c", tg_chat_id="-100123", language="ru", mode="auto",
        cron="0 * * * *", format="single", max_per_run=3,
    )  # fmt: skip
    return Channel(**{**base, **kw})  # type: ignore[arg-type]


def cand(**kw: object) -> Candidate:
    base: dict[str, object] = dict(
        event_id=uuid.uuid4(), status="NEW", relevance="HIGH", reliability="MEDIUM",
        region="BR", sport_id="football", source_ids=[GE],
    )  # fmt: skip
    return Candidate(**{**base, **kw})  # type: ignore[arg-type]


def test_schedule() -> None:
    assert is_due(ch(), NOW)  # новый канал — сразу
    assert not is_due(ch(last_run_at=datetime(2026, 10, 9, 18, 0, tzinfo=UTC)), NOW)
    assert is_due(ch(last_run_at=datetime(2026, 10, 9, 17, 0, tzinfo=UTC)), NOW)


def test_filters() -> None:
    tiers = {GE: "A", BLOG: "UNTRUSTED"}
    assert matches(ch(), cand(), tiers)
    assert not matches(ch(mode="approval"), cand(), tiers)  # approval — только READY
    assert matches(ch(mode="approval"), cand(status="READY", reliability="LOW"), tiers)
    assert not matches(ch(min_trust="HIGH"), cand(), tiers)
    assert not matches(ch(regions=["PT"]), cand(), tiers)
    assert not matches(ch(sports=["tennis"]), cand(), tiers)
    assert not matches(ch(source_deny=[GE]), cand(), tiers)
    assert not matches(ch(source_allow=[BLOG]), cand(), tiers)
    assert not matches(ch(min_tier="A"), cand(source_ids=[BLOG]), tiers)
    assert matches(ch(min_tier="A"), cand(source_ids=[BLOG, GE]), tiers)


def test_digest_escapes_and_links() -> None:
    out = render_digest([DigestItem("A & B", "https://x/1"), DigestItem("C", None)], "ru")
    assert out == '<b>Главное</b>\n\n• <a href="https://x/1">A &amp; B</a>\n• C'


def test_next_runs() -> None:
    at = lambda h, m=0: datetime(2026, 10, 9, h, m, tzinfo=UTC)  # noqa: E731
    # новый канал — сразу, дальше по cron
    assert next_runs(ch(cron="0 9,18 * * *"), NOW, 3) == [
        NOW,
        datetime(2026, 10, 10, 9, tzinfo=UTC),
        datetime(2026, 10, 10, 18, tzinfo=UTC),
    ]
    # следующий слот после прошлого запуска
    assert next_runs(ch(last_run_at=at(18, 0)), NOW, 2) == [at(19), at(20)]
    # пропущенный слот — «сейчас» (worker подхватит в течение минуты)
    assert next_runs(ch(last_run_at=at(16, 0)), NOW, 2)[0] == NOW
