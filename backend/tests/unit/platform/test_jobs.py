import pytest

from sportintel.platform import jobs


@pytest.mark.parametrize("name", ["platform.heartbeat", "ingestion.fetch_source"])
def test_known_names_accepted(name: str) -> None:
    jobs.validate_task_name(name)


@pytest.mark.parametrize("name", ["Platform.x", "platform", "a.b.c", "platform.Heart"])
def test_bad_format_rejected(name: str) -> None:
    with pytest.raises(ValueError, match="invalid task name"):
        jobs.validate_task_name(name)


def test_name_outside_catalog_rejected() -> None:
    with pytest.raises(ValueError, match="catalog"):
        jobs.validate_task_name("platform.not_in_catalog")


def test_unknown_queue_rejected() -> None:
    with pytest.raises(ValueError, match="queue"):
        jobs.task("platform.heartbeat", queue="nope")


def test_retry_doubles_wait_and_stops_at_max_attempts() -> None:
    policy = jobs.RetryPolicy(max_attempts=3, exponential_wait_s=60)
    err = jobs.TransientError()
    assert [policy.delay_s(err, a) for a in (0, 1, 2)] == [60, 120, None]


def test_non_transient_not_retried() -> None:
    assert jobs.RetryPolicy(max_attempts=5, exponential_wait_s=1).delay_s(ValueError(), 0) is None


def test_no_policy_no_strategy() -> None:
    assert jobs.retry_strategy(None) is None


def test_conninfo_strips_driver_and_keeps_socket() -> None:
    assert (
        jobs.conninfo("postgresql+psycopg://u:p@localhost:5432/db")
        == "postgresql://u:p@localhost:5432/db"
    )
    sock = jobs.conninfo("postgresql+psycopg://app:pwd@/db?host=/cloudsql/p:r:i")
    assert sock.startswith("postgresql://app:pwd@/db?host=")
    assert "cloudsql" in sock
