"""Ограничение частоты дорогих действий (BE-T5.5): скользящее окно в памяти процесса."""

import math
import time
from collections import defaultdict, deque

from sportintel.platform.errors import RateLimited

# ponytail: лимит на инстанс web; общий счётчик (Redis) — когда инстансов web станет больше двух (D8).
_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
AI_GENERATE = ("ai_generate", 10, 60)


def check(
    key: str, subject: object, per_user: int, window_s: int, now: float | None = None
) -> None:
    """Превышение → RateLimited (429 common.rate_limited + Retry-After)."""
    t = time.monotonic() if now is None else now
    q = _hits[(key, str(subject))]
    while q and q[0] <= t - window_s:
        q.popleft()
    if len(q) >= per_user:
        raise RateLimited(
            f"{key}: at most {per_user} per {window_s}s",
            retry_after_s=max(1, math.ceil(q[0] + window_s - t)),
        )
    q.append(t)


def limit_ai_generate(subject: object) -> None:
    key, n, w = AI_GENERATE
    check(key, subject, n, w)


def reset() -> None:
    _hits.clear()
