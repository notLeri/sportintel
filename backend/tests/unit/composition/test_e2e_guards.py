import pytest

from sportintel.composition.e2e_cli import guard, tables_to_truncate


def test_refuses_outside_e2e() -> None:
    for env in ("staging", "prod", "local", "ci"):
        with pytest.raises(SystemExit) as e:
            guard(env)
        assert e.value.code == 2
    guard("e2e")


def test_tables_from_registry_keep_dictionaries() -> None:
    tables = tables_to_truncate()
    assert "events.events" in tables
    assert "editorial.telegram_drafts" in tables
    assert not [t for t in tables if t.startswith("taxonomy.")]
    assert "platform.app_settings" not in tables
