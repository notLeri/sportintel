import uuid

import pytest

from sportintel.modules.events.domain.policies.reliability import (
    SourceEvidence,
    compute_reliability,
)
from sportintel.modules.events.domain.values import Reliability as L
from sportintel.modules.events.domain.values import ReliabilityFactor as F


def ev(
    tier: str | None,
    group: str | None,
    *,
    rumor: bool = False,
    clickbait: bool = False,
    dup: bool = False,
) -> SourceEvidence:
    return SourceEvidence(
        uuid.uuid4(),
        uuid.uuid5(uuid.NAMESPACE_DNS, group or "x"),
        tier,
        group,
        dup,
        rumor,
        clickbait,
    )


@pytest.mark.parametrize(
    ("items", "conflicts", "level", "first"),
    [
        ([], 0, L.UNKNOWN, F.NO_ARTICLES),
        ([ev("OFFICIAL", "cbf")], 0, L.HIGH, F.OFFICIAL_CONFIRMED),
        (
            [ev("OFFICIAL", "cbf"), ev("A", "globo")],
            1,
            L.MEDIUM,
            F.INDEPENDENT_TIER_A_2PLUS,
        ),  # конфликт: без official_confirmed, cap
        ([ev("A", "globo"), ev("A", "uol")], 0, L.HIGH, F.INDEPENDENT_TIER_A_2PLUS),
        (
            [ev("A", "globo"), ev("A", "globo")],
            0,
            L.MEDIUM,
            F.SINGLE_TIER_A,
        ),  # одна группа (Globo+GE)
        ([ev("B", "lance"), ev("B", "cnn")], 0, L.MEDIUM, F.INDEPENDENT_TIER_B_2PLUS),
        ([ev("B", "lance"), ev("C", "blog")], 0, L.LOW, F.SINGLE_SOURCE),
        ([ev("C", "a"), ev("C", "b")], 0, L.LOW, F.TIER_C_ONLY),
        ([ev(None, None)], 0, L.UNKNOWN, F.UNKNOWN_TIER),
        ([ev("A", "globo", rumor=True), ev("A", "uol", rumor=True)], 0, L.LOW, F.RUMOR_MARKERS),
        (
            [ev("A", "globo", clickbait=True), ev("A", "uol", clickbait=True)],
            0,
            L.MEDIUM,
            F.INDEPENDENT_TIER_A_2PLUS,
        ),
        ([ev("A", "globo"), ev("A", "uol", dup=True)], 0, L.MEDIUM, F.SINGLE_TIER_A),
    ],
)
def test_table(items: list[SourceEvidence], conflicts: int, level: L, first: F) -> None:
    r = compute_reliability(items, conflicts)
    assert (r.level, r.factors[0].code) == (level, first)


def test_conflict_cap_and_clickbait_factors() -> None:
    r = compute_reliability([ev("A", "globo", clickbait=True), ev("A", "uol", clickbait=True)], 0)
    assert [f.code for f in r.factors] == [F.INDEPENDENT_TIER_A_2PLUS, F.CLICKBAIT]
    capped = compute_reliability([ev("A", "globo"), ev("A", "uol")], 2)
    assert (capped.level, capped.factors[-1].code) == (L.MEDIUM, F.OPEN_CONFLICT_CAP)


def test_untrusted_sources_confirm_nothing() -> None:
    only = compute_reliability([ev("UNTRUSTED", "blog"), ev("UNTRUSTED", "blog2")], 0)
    assert (only.level, only.factors[0].code) == (L.LOW, F.UNTRUSTED_ONLY)
    # недоверенный рядом с одним A не превращает событие в «2+ независимых»
    mixed = compute_reliability([ev("A", "globo"), ev("UNTRUSTED", "blog")], 0)
    assert (mixed.level, mixed.factors[0].code) == (L.MEDIUM, F.SINGLE_TIER_A)
