"""Пробный fetch источника без сохранения статей (BE-T4.8)."""

import asyncio
import json
import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy import text

from sportintel.modules.ingestion.application.fetch_source import Fetcher, Profile, expand_years
from sportintel.modules.sources import public as sources
from sportintel.platform.clock import Clock, SystemClock
from sportintel.platform.db import Database
from sportintel.platform.safe_fetch import FetchError, FetchRequest
from sportintel.platform.safe_fetch.port import Accept

MAX_ITEMS = 10


async def preview_fetch(
    db: Database,
    preview_id: uuid.UUID,
    fetcher: Fetcher,
    profile_for: Callable[[str], Profile],
    extract: Callable[[bytes, str, str], Any],
    clock: Clock | None = None,
) -> None:
    async with db.uow() as uow:
        row = (
            await uow.session.execute(
                text("SELECT source_id, status FROM ingestion.preview_results WHERE id = :i"),
                {"i": preview_id},
            )
        ).first()
        if row is None or row.status != "pending":
            return
        meta = await sources.get_source_meta(uow, row.source_id)
    profile = profile_for(meta.parser_profile)
    accept: Accept = {"html": "html", "calendar": "any"}.get(meta.kind, "feed")  # type: ignore[assignment]
    feeds: list[dict[str, Any]] = []
    first_url: str | None = None
    for feed_url in expand_years(meta.feed_urls, (clock or SystemClock()).now(), None):
        try:
            resp = await fetcher.fetch(
                FetchRequest(feed_url, accept), min_gap_ms=meta.min_request_gap_ms
            )
            items = profile.list_items(resp.body, resp.content_type, resp.final_url)[:MAX_ITEMS]
            feeds.append(
                {
                    "feed_url": feed_url,
                    "status": "ok",
                    "error_code": None,
                    "items": [
                        {
                            "url": i.url,
                            "title": i.title,
                            "published_at": i.published_at.isoformat() if i.published_at else None,
                        }
                        for i in items
                    ],
                }
            )
            first_url = first_url or (items[0].url if items else None)
        except FetchError as e:
            feeds.append(
                {"feed_url": feed_url, "status": "error", "error_code": e.code, "items": []}
            )
        except Exception as e:
            feeds.append(
                {
                    "feed_url": feed_url,
                    "status": "error",
                    "error_code": f"parse_{type(e).__name__}",
                    "items": [],
                }
            )
    sample = None
    if first_url:
        try:
            page_resp = await fetcher.fetch(
                FetchRequest(first_url, "html"), min_gap_ms=meta.min_request_gap_ms
            )
            page = await asyncio.to_thread(
                extract, page_resp.body, page_resp.final_url, meta.parser_profile
            )
            sample = {
                "url": first_url,
                "title": page.title,
                "lead": page.description,
                "published_at": page.published_at.isoformat()
                if getattr(page, "published_at", None)
                else None,
                "image_url": getattr(page, "image_url", None),
                "text_chars": len(page.text or ""),
            }
        except FetchError as e:
            sample = {"url": first_url, "error_code": e.code}
        except Exception as e:
            sample = {"url": first_url, "error_code": f"extract_{type(e).__name__}"}
    status = "ok" if any(f["status"] == "ok" for f in feeds) else "error"
    async with db.uow() as uow:
        await uow.session.execute(
            text(
                "UPDATE ingestion.preview_results SET status = :s, result = CAST(:r AS jsonb) WHERE id = :i"
            ),
            {"s": status, "r": json.dumps({"feeds": feeds, "sample": sample}), "i": preview_id},
        )
