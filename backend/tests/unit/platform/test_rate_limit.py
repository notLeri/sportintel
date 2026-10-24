import pytest

from sportintel.platform import rate_limit
from sportintel.platform.errors import RateLimited


def test_sliding_window_and_retry_after() -> None:
    for i in range(10):
        rate_limit.check("k", "u1", 10, 60, now=100 + i)
    with pytest.raises(RateLimited) as e:
        rate_limit.check("k", "u1", 10, 60, now=110)
    assert e.value.retry_after_s == 50
    rate_limit.check("k", "u2", 10, 60, now=110)  # другой пользователь
    rate_limit.check("k", "u1", 10, 60, now=160.5)  # первое окно истекло
