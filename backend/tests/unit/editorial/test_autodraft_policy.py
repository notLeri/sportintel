from types import SimpleNamespace as NS

import pytest

from sportintel.modules.editorial.application.autodraft import DraftSnapshot, decide

C = NS(basis_hash="h2", has_articles=True)


@pytest.mark.parametrize(
    ("snap", "cand", "want"),
    [
        (None, C, "create"),
        (None, NS(basis_hash="h", has_articles=False), "skip"),
        (DraftSnapshot(None, "ready", "h1", False), C, "rebuild"),
        (DraftSnapshot(None, "ready", "h2", False), C, "skip"),
        (DraftSnapshot(None, "ready", "h1", True), C, "skip"),
        (DraftSnapshot("user", "ready", "h1", False), C, "skip"),
        (DraftSnapshot(None, "failed", "h1", False), C, "skip"),
    ],
)
def test_decide(snap: DraftSnapshot | None, cand: NS, want: str) -> None:
    assert decide(snap, cand) == want
