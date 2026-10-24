"""Детерминированный экспорт контракта API в `openapi.json` (BE-T0.9).

python scripts/export_openapi.py          # записать
python scripts/export_openapi.py --check  # код 1, если файл устарел
"""

import argparse
import json
import sys
from pathlib import Path

from sportintel.main import create_app
from sportintel.platform.config import Settings

OUTPUT = Path(__file__).resolve().parents[2] / "openapi.json"


def render() -> str:
    # Фиксированные настройки: схема не зависит от окружения разработчика; БД не нужна.
    # e2e — чтобы в контракт попал /auth/dev-login (FE и Playwright логинятся через него).
    settings = Settings(
        env="e2e",
        dev_login_enabled=True,
        version="1",
        database_url="postgresql+psycopg://openapi:openapi@localhost/openapi",
        app_base_url="http://localhost:8000",
        log_level="WARNING",
    )
    schema = create_app(settings).openapi()
    schema["info"]["version"] = "1"
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if openapi.json is stale")
    args = parser.parse_args()
    content = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != content:
            print("openapi.json устарел: выполните `make openapi`", file=sys.stderr)
            return 1
        return 0
    OUTPUT.write_text(content)
    return 0


if __name__ == "__main__":
    sys.exit(main())
