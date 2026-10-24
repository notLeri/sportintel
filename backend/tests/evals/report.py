from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from sportintel.platform.clock import SystemClock

REPORTS = Path(__file__).resolve().parents[3] / "evals" / "reports"


def _today() -> str:
    return SystemClock().now().astimezone(ZoneInfo("America/Sao_Paulo")).date().isoformat()


def write(
    name: str, title: str, summary: dict[str, Any], targets: dict[str, float], misses: list[str]
) -> Path:
    lines = [
        f"# {title}",
        "",
        f"Дата: {_today()}",
        "",
        "| Метрика | Значение | Цель |",
        "|---|---|---|",
    ]
    for k, v in summary.items():
        val = f"{v:.3f}" if isinstance(v, float) else str(v)
        goal = f"≥ {targets[k]}" if k in targets else ""
        lines.append(f"| {k} | {val} | {goal} |")
    ok = all(summary[k] >= t for k, t in targets.items())
    lines += ["", f"**Итог:** {'цели достигнуты' if ok else 'цели НЕ достигнуты'}", ""]
    if misses:
        lines += ["## Ошибки", "", *(f"- {m}" for m in misses), ""]
    path = REPORTS / f"{_today()}_{name}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
