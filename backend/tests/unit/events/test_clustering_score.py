import uuid

from sportintel.modules.events.domain.policies.clustering import (
    ArticleFeatures,
    CandidateRow,
    decide,
    score,
)
from sportintel.modules.events.domain.values import EventStatus
from sportintel.platform.settings_store import Clustering

P = Clustering()
P_EMB = Clustering(
    t_high=0.82, t_low=0.60
)  # пороги режима эмбеддингов — откалибровать в фазе L (ADR-003)
E1, E2, E3, COMP = (uuid.uuid4() for _ in range(4))


def cand(
    cos: float | None, ents: set[uuid.UUID], lex: float = 0.0, comp: uuid.UUID | None = COMP
) -> CandidateRow:
    return CandidateRow(uuid.uuid4(), cos, comp, frozenset(ents), EventStatus.NEW, lex)


def test_embedding_mode() -> None:
    a = ArticleFeatures([0.1], frozenset({E1, E2}), COMP, "football")
    best = score(a, cand(0.95, {E1, E2}), False, P_EMB)
    assert decide(best, P_EMB) == "attach"
    assert (
        decide(score(a, cand(0.95, {E1, E2}), True, P_EMB), P_EMB) == "gray"
    )  # конфликт claims тянет вниз


def test_lexical_mode_is_normalized() -> None:
    a = ArticleFeatures(None, frozenset({E1, E2}), COMP, "football")
    assert score(a, cand(None, {E1, E2}, lex=1.0), False, P) == 1.0
    assert decide(score(a, cand(None, {E3}, lex=0.2, comp=None), False, P), P) == "new"
    mid = score(a, cand(None, {E1, E3}, lex=0.6), False, P)
    assert 0 < mid < 1


def test_decide_edges() -> None:
    assert decide(None, P) == "new"
    assert decide(P.t_low, P) == "new"
    assert decide(P.t_high, P) == "attach"
    assert decide((P.t_low + P.t_high) / 2, P) == "gray"
