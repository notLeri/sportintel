"""Keyset-пагинация с типизированным cursor (CONV §5.1, BE-T1.11)."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sportintel.platform.errors import FieldError, ValidationFailed
from sportintel.platform.http_api import decode_cursor as _decode
from sportintel.platform.http_api import encode_cursor as _encode

CursorValue = str | int | float | datetime | uuid.UUID | None


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    next_cursor: str | None


def encode_cursor(values: Sequence[CursorValue]) -> str:
    plain: list[str | int | float | None] = []
    for v in values:
        if isinstance(v, datetime):
            plain.append(v.isoformat())
        elif isinstance(v, uuid.UUID):
            plain.append(str(v))
        else:
            plain.append(v)
    return _encode(tuple(plain))


def decode_cursor(cursor: str, types: Sequence[type]) -> tuple[Any, ...]:
    raw = _decode(cursor, len(types))
    out: list[Any] = []
    try:
        for value, kind in zip(raw, types, strict=True):
            if value is None:
                out.append(None)
            elif kind is datetime:
                out.append(datetime.fromisoformat(str(value)))
            elif kind is uuid.UUID:
                out.append(uuid.UUID(str(value)))
            else:
                out.append(kind(value))
    except (ValueError, TypeError):
        raise ValidationFailed(
            details=[FieldError("cursor", "invalid", "invalid cursor")]
        ) from None
    return tuple(out)


def split_multi(values: Sequence[str] | None) -> list[str]:
    """Повторяющийся параметр или значения через запятую — эквивалентны (CONV §5.1)."""
    return [p.strip() for v in values or [] for p in v.split(",") if p.strip()]
