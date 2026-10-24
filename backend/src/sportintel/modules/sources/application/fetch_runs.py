"""История опросов источника и результат опроса (BE-T1.6; health/backoff — BE-T1.9)."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

RunStatus = Literal["ok", "not_modified", "error", "skipped"]


@dataclass(frozen=True)
class FetchRunRecord:
    id: uuid.UUID
    source_id: uuid.UUID
    feed_url: str | None
    started_at: datetime
    finished_at: datetime | None
    status: RunStatus
    http_status: int | None = None
    items_seen: int = 0
    items_new: int = 0
    error_code: str | None = None
    error_detail: str | None = None


class FetchRunStore(Protocol):
    async def insert(self, run: FetchRunRecord) -> None: ...
    async def page(
        self, source_id: uuid.UUID, after: tuple[datetime, uuid.UUID] | None, limit: int
    ) -> list[FetchRunRecord]: ...
