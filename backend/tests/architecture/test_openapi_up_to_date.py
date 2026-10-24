import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]


def test_openapi_json_is_up_to_date() -> None:
    r = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--check"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stderr
