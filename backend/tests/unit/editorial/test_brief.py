import uuid
from dataclasses import dataclass, field

import pytest

from sportintel.modules.editorial.application.brief import (
    BriefSource,
    EventBrief,
    brief_prompt,
    ground,
    render_tg,
)
from sportintel.platform.llm import FakeProvider, LlmError, _validated


@dataclass
class Src:
    source_name: str
    tier: str | None
    url: str
    title: str
    lead: str | None
    article_id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class Pack:
    title: str
    sources: list[Src]
    fragments: list[object] = field(default_factory=list)


BRIEF = EventBrief(
    headline="Педро травмирован и пропустит дерби",
    status="confirmed",
    summary=["Фламенго подтвердил травму бедра у Педро.", "Он пропустит дерби."],
    affected=["Фламенго", "Педро"],
    impact="Атака Фламенго ослаблена <перед матчем>.",
    actions=["Следить за официальным составом"],
    source_refs=[2, 9, 1, 2],
)


def test_prompt_numbers_sources_and_names_target_language() -> None:
    pack = Pack(
        "Flamengo confirma lesão de Pedro",
        [
            Src("ge", "A", "https://ge/x", "Flamengo confirma lesão", "Atacante sentiu dores."),
            Src("Lance", "B", "https://lance/y", "Pedro vira desfalque", None),
        ],
    )
    system, user, srcs = brief_prompt(pack, "ru")
    assert "Russian" in system
    assert "[1] ge (trust tier: A)" in user
    assert "[2] Lance" in user
    assert [s.n for s in srcs] == [1, 2]


SRCS = [BriefSource(1, "ge", "A", "https://ge/x"), BriefSource(2, "Lance", "B", "https://l/y")]


def test_ground_keeps_only_existing_sources_once() -> None:
    assert ground(BRIEF, SRCS).source_refs == [2, 1]  # type: ignore[union-attr]
    assert ground(BRIEF.model_copy(update={"source_refs": [7]}), SRCS) is None


def test_confirmed_needs_two_outlets() -> None:
    one = ground(BRIEF.model_copy(update={"source_refs": [1]}), SRCS)
    assert one is not None
    assert one.status == "reported"
    assert ground(BRIEF, SRCS).status == "confirmed"  # type: ignore[union-attr]


def test_render_links_come_from_sources_and_text_is_escaped() -> None:
    out = render_tg(ground(BRIEF, SRCS), SRCS, "ru", "⚽", "2026-10-09")  # type: ignore[arg-type]
    assert out.startswith("<b>⚽ Педро травмирован")
    assert "<i>2026-10-09</i>" in out
    assert "Статус" not in out  # статус проверки — только редактору
    assert "подтвержд" not in out
    assert "&lt;перед матчем&gt;" in out
    assert 'Источники: <a href="https://l/y">Lance</a>, <a href="https://ge/x">ge</a>' in out


async def test_invalid_json_is_retried_once_then_fails() -> None:
    answers = iter(['{"headline": 1}', '{"broken"'])

    async def call() -> str:
        return next(answers)

    with pytest.raises(LlmError):
        await _validated(call, EventBrief)


async def test_fake_provider_returns_schema_instance() -> None:
    fake = FakeProvider({"EventBrief": BRIEF.model_dump()})
    got = await fake.complete_json("s", "u", EventBrief)
    assert got.headline == BRIEF.headline
    assert fake.calls == [("s", "u")]
