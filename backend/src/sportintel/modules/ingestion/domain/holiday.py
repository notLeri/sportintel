"""Отпечаток официального праздника: один и тот же праздник из разных источников — одно событие."""

import hashlib
import re
from datetime import date

_SCOPE = re.compile(r"\(([A-Z]{2}-[A-Z0-9-]+(?:, [A-Z]{2}-[A-Z0-9-]+)*)\)$")


def fingerprint(country: str, day: date, title: str) -> int:
    """Отпечаток праздника для поиска перепечаток: одинаков у всех источников, 64 бита со знаком.

    Не simhash: близкие строки («…-10-12» и «…-10-13») дали бы близкие хеши и ложные дубли."""
    m = _SCOPE.search(title)
    raw = f"holiday|{country}|{day.isoformat()}|{m.group(1) if m else 'national'}"
    return int.from_bytes(hashlib.sha256(raw.encode()).digest()[:8], "big", signed=True)
