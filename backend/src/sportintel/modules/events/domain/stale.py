"""Подозрение на старую новость (BE-T4.6)."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

BRT = ZoneInfo("America/Sao_Paulo")
STALE_DAYS = 3


def is_stale_by_hint(hints: list[date | None], occurred_at: datetime) -> bool:
    """Хотя бы у половины статей с подсказкой даты: hint раньше дня события (BRT) более чем на 3 дня."""
    known = [h for h in hints if h is not None]
    if not known:
        return False
    limit = occurred_at.astimezone(BRT).date() - timedelta(days=STALE_DAYS)
    return sum(h < limit for h in known) * 2 >= len(known)
