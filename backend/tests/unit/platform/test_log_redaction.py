import json

import structlog

from sportintel.platform.config import Settings
from sportintel.platform.logging import configure_logging


def test_cookie_and_csrf_values_are_not_logged(capsys) -> None:  # type: ignore[no-untyped-def]
    configure_logging(
        Settings(
            env="ci",
            database_url="postgresql+psycopg://u:p@h/db",
            app_base_url="http://t",
            log_format="json",
        )
    )
    structlog.get_logger("t").info(
        "request",
        headers={"Cookie": "sid=SECRET1", "X-CSRF-Token": "SECRET2", "Accept": "text/html"},
        authorization="Bearer SECRET3",
    )
    out = capsys.readouterr().out
    assert "SECRET" not in out
    line = json.loads(out.strip().splitlines()[-1])
    assert line["headers"]["Accept"] == "text/html"
    assert line["headers"]["Cookie"] == "[redacted]"
