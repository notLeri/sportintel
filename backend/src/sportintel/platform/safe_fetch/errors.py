from typing import Literal

FailureCode = Literal[
    "fetch_http_4xx",
    "fetch_http_5xx",
    "fetch_timeout",
    "fetch_too_large",
    "fetch_bad_content_type",
    "fetch_network",
    "ssrf_blocked",
    "blocked_by_robots",
]


class FetchError(Exception):
    """Сбой загрузки с кодом CONV §6.2. permanent=True — повтор не поможет."""

    def __init__(self, code: FailureCode, detail: str, *, permanent: bool) -> None:
        super().__init__(f"{code}: {detail}")
        self.code: FailureCode = code
        self.detail = detail[:500]
        self.permanent = permanent
