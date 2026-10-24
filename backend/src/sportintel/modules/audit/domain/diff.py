"""diff и JSON-нормализация значений для аудита (BE-T3.1). Чистые функции."""

import json
import uuid
from collections.abc import Mapping
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

MAX_JSON_BYTES = 64 * 1024
TEXT_CLIP = 2000
TRUNCATED = "…[truncated]"


def to_json(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, datetime | date):
        return v.isoformat()
    if isinstance(v, uuid.UUID):
        return str(v)
    if is_dataclass(v) and not isinstance(v, type):
        return to_json(asdict(v))
    if isinstance(v, Mapping):
        return {str(k): to_json(x) for k, x in v.items()}
    if isinstance(v, list | tuple | set | frozenset):
        items = [to_json(x) for x in v]
        return sorted(items, key=str) if isinstance(v, set | frozenset) else items
    return v


def diff(
    before: Mapping[str, Any], after: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Только изменённые ключи; вложенные структуры сравниваются целиком."""
    b, a = to_json(before), to_json(after)
    keys = [k for k in {**b, **a} if b.get(k) != a.get(k)]
    return {k: b.get(k) for k in keys}, {k: a.get(k) for k in keys}


def clip(v: Any) -> Any:
    """> 64 КБ JSON → текстовые поля обрезаются до 2000 символов с пометкой."""
    if v is None or len(json.dumps(v, ensure_ascii=False)) <= MAX_JSON_BYTES:
        return v

    def cut(x: Any) -> Any:
        if isinstance(x, str) and len(x) > TEXT_CLIP:
            return x[:TEXT_CLIP] + TRUNCATED
        if isinstance(x, dict):
            return {k: cut(y) for k, y in x.items()}
        if isinstance(x, list):
            return [cut(y) for y in x]
        return x

    return cut(v)
