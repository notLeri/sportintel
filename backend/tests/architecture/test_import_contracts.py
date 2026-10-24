import os
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).parent / "fixtures"
LINT_IMPORTS = Path(sys.executable).with_name("lint-imports")


def _run(*args: str, cwd: Path, extra_path: Path | None = None) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)  # noqa: TID251 — тест запускает CLI в подпроцессе
    if extra_path:
        env["PYTHONPATH"] = f"{extra_path}{os.pathsep}{env.get('PYTHONPATH', '')}"
    return subprocess.run(  # noqa: S603 — фиксированный бинарь из venv
        [str(LINT_IMPORTS), *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
    )


def test_contracts_kept() -> None:
    r = _run(cwd=BACKEND)
    assert r.returncode == 0, r.stdout + r.stderr


def test_violation_is_caught() -> None:
    r = _run("--config", str(FIXTURES / "importlinter.ini"), cwd=FIXTURES, extra_path=FIXTURES)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "BROKEN" in r.stdout
    assert "bad_pkg.modules.editorial.service -> bad_pkg.modules.events.domain.model" in r.stdout
