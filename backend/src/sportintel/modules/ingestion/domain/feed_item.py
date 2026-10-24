from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class FeedItem:
    url: str
    title: str
    summary: str | None
    published_at: datetime | None
    image_url: str | None
    author: str | None
