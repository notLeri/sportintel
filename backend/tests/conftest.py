import functools
from collections.abc import Iterator
from typing import Any

import pytest
import sentry_sdk
from sentry_sdk.transport import Transport

from sportintel.platform.config import Settings, get_settings

pytest_plugins = ["tests.db_fixtures"]

DB_URL = "postgresql+psycopg://app:app@localhost:5432/sportintel_test"


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    return Settings(env="ci", database_url=DB_URL, app_base_url="http://testserver")


class CaptureTransport(Transport):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[dict[str, Any]] = []

    def capture_envelope(self, envelope: Any) -> None:
        for item in envelope.items:
            if item.type == "event":
                self.events.append(item.payload.json)


@pytest.fixture
def captured(monkeypatch: pytest.MonkeyPatch) -> Iterator[CaptureTransport]:
    transport = CaptureTransport()
    monkeypatch.setattr(sentry_sdk, "init", functools.partial(sentry_sdk.init, transport=transport))
    yield transport
    sentry_sdk.init()  # выключить клиента для следующих тестов


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """evals запускаются только явно: make evals (pytest -m evals)."""
    if "evals" in (config.option.markexpr or ""):
        return
    skip = pytest.mark.skip(reason="evals: только make evals")
    for item in items:
        if "evals" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _reset_rate_limits() -> None:
    from sportintel.platform import rate_limit

    rate_limit.reset()
