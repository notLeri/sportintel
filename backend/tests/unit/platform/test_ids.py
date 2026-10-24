from sportintel.platform.ids import new_id


def _unix_ms(u) -> int:
    return u.int >> 80


def test_version_variant_and_uniqueness() -> None:
    ids = [new_id() for _ in range(1000)]
    assert len(set(ids)) == 1000
    assert all(u.version == 7 for u in ids)
    assert all(u.variant == "specified in RFC 4122" for u in ids)


def test_timestamps_non_decreasing() -> None:
    stamps = [_unix_ms(new_id()) for _ in range(1000)]
    assert stamps == sorted(stamps)
