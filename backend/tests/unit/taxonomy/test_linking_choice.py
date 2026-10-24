import uuid

from sportintel.modules.taxonomy.domain.linking import Candidate, choose, is_ambiguous

A, B, C = uuid.UUID(int=1), uuid.UUID(int=2), uuid.UUID(int=3)


def cand(eid: uuid.UUID, sport: str | None = "football", priority: int = 0) -> Candidate:
    return Candidate(eid, "team", sport, priority, 1.0, "x")


def test_sport_first_then_priority() -> None:
    assert (
        choose([cand(A, "basketball", 2), cand(B, "football", 0)], set(), "football").entity_id == B
    )  # type: ignore[union-attr]
    assert choose([cand(A, priority=0), cand(B, priority=2)], set(), "football").entity_id == B  # type: ignore[union-attr]


def test_context_then_id() -> None:
    assert choose([cand(A), cand(B)], {B}, "football").entity_id == B  # type: ignore[union-attr]
    assert choose([cand(C), cand(B)], set(), "football").entity_id == B  # type: ignore[union-attr]


def test_empty_and_ambiguity() -> None:
    assert choose([], set()) is None
    cs = [cand(A), cand(B)]
    best = choose(cs, set(), "football")
    assert best is not None
    assert is_ambiguous(cs, best, "football")
    assert not is_ambiguous([cand(A, priority=2), cand(B)], cand(A, priority=2), "football")
