import uuid
from collections.abc import Callable
from typing import Any

from sportintel.modules.editorial.disclaimers import render
from sportintel.modules.editorial.domain.limits import max_length, plain_length
from sportintel.platform.db import UnitOfWork
from sportintel.platform.errors import NotFound

RepoFor = Callable[[UnitOfWork], Any]


def version_dto(
    v: dict[str, Any], ui_language: str, source_names: dict[str, str]
) -> dict[str, Any]:
    """Дисклеймер видит только редактор — он на языке интерфейса, а не поста."""
    kinds = list(v["disclaimer_kinds"])
    return {
        "n": v["n"],
        "lang": v.get("lang") or ui_language,
        "body_tg_html": v["body_tg_html"],
        "image_url": v["image_url"],
        "disclaimer_kinds": kinds,
        "disclaimer_removed": v["disclaimer_removed"],
        "disclaimer_text": None if v["disclaimer_removed"] else render(kinds, ui_language),
        "origin": v["origin"],
        "citations": [
            {**c, "source_name": source_names.get(str(c["article_id"]), "")} for c in v["citations"]
        ],
        "grounding": v["grounding_report"],
        "author_id": v["author_id"],
        "created_at": v["created_at"],
        "plain_length": plain_length(v["body_tg_html"]),
        "max_length": max_length(v["image_url"] is not None),
    }


async def draft_detail(
    uow: UnitOfWork,
    repo_for: RepoFor,
    draft_id: uuid.UUID,
    language: str,
    source_names: dict[str, str],
) -> dict[str, Any]:
    repo = repo_for(uow)
    d = await repo.get(draft_id)
    if d is None:
        raise NotFound(f"draft {draft_id} not found")
    cur = await repo.version(draft_id, d["current_version"]) if d["current_version"] else None
    return {
        "id": d["id"],
        "event_id": d["event_id"],
        "state": d["state"],
        "failure_code": d["failure_code"],
        "current": version_dto(cur, language, source_names) if cur else None,
        "versions": await repo.versions(draft_id),
        "version": d["version"],
        "auto": d["created_by"] is None,
    }
