"""SSRF-безопасный HTTP-клиент (BE-T1.3). Модули ходят в сеть только через него."""

from sportintel.platform.safe_fetch.adapter import SafeHttpFetcher
from sportintel.platform.safe_fetch.errors import FailureCode, FetchError
from sportintel.platform.safe_fetch.fake import FakeHttpFetcher
from sportintel.platform.safe_fetch.politeness import PoliteFetcher
from sportintel.platform.safe_fetch.port import FetchRequest, FetchResponse, HttpFetcher

__all__ = [
    "FailureCode",
    "FakeHttpFetcher",
    "FetchError",
    "FetchRequest",
    "FetchResponse",
    "HttpFetcher",
    "PoliteFetcher",
    "SafeHttpFetcher",
]
