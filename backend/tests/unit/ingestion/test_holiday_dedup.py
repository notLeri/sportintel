from datetime import date

from sportintel.modules.ingestion.domain.holiday import fingerprint
from sportintel.modules.ingestion.infrastructure.parsers.holidays import holiday_item


def _fp(name: str, day: date, regions: list[str]) -> int:
    item = holiday_item("https://x.test/feed", day, name, "BR", regions)
    return fingerprint("BR", day, item.title)


def test_same_holiday_from_two_sites_is_one_event() -> None:
    # OpenHolidays пишет по-английски, BrasilAPI — по-португальски: отпечаток один.
    day = date(2026, 10, 12)
    assert _fp("Our Lady of Aparecida", day, []) == _fp("Nossa Senhora Aparecida", day, [])


def test_other_day_or_region_is_another_event() -> None:
    day = date(2026, 10, 12)
    national = _fp("Nossa Senhora Aparecida", day, [])
    assert national != _fp("Nossa Senhora Aparecida", date(2026, 10, 13), [])
    assert national != _fp("Dia do Estado", day, ["BR-SP"])
    assert _fp("A", day, ["BR-SP", "BR-RJ"]) == _fp("B", day, ["BR-RJ", "BR-SP"])
