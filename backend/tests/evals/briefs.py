"""Сравнение моделей на брифах: валидность JSON, опора на источники, время; тексты — для ручной оценки.

uv run --env-file ../.env python -m tests.evals.briefs ../evals/datasets/briefs_v1.jsonl \
    --models ollama:qwen3:14b ollama:gemma3:12b [anthropic:claude-haiku-5-5] --lang ru
"""

import argparse
import asyncio
import json
import statistics
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sportintel.modules.editorial.application.brief import (
    EventBrief,
    brief_prompt,
    ground,
    render_tg,
)
from sportintel.platform.clock import SystemClock
from sportintel.platform.config import load_settings_or_exit
from sportintel.platform.llm import AnthropicProvider, LlmError, LlmProvider, OllamaProvider


@dataclass
class Src:
    source_name: str
    tier: str | None
    url: str
    title: str
    lead: str | None
    article_id: Any


@dataclass
class Frag:
    article_id: Any
    text: str


@dataclass
class Pack:
    title: str
    sources: list[Src]
    fragments: list[Frag] = field(default_factory=list)


def load(path: str) -> list[tuple[str, Pack]]:
    out = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        srcs = [
            Src(
                s["source_name"],
                s["tier"],
                s["url"],
                s["title"],
                s["lead"],
                uuid.UUID(s["article_id"]),
            )
            for s in r["sources"]
        ]
        frags = [
            Frag(uuid.UUID(s["article_id"]), s["fragment"])
            for s in r["sources"]
            if s.get("fragment")
        ]
        out.append((r["event_id"], Pack(r["title"], srcs, frags)))
    return out


def provider(spec: str) -> LlmProvider:
    kind, model = spec.split(":", 1)
    s = load_settings_or_exit()
    if kind == "ollama":
        return OllamaProvider(s.ollama_url, model, s.ollama_timeout_s, 1)
    if kind == "anthropic" and s.anthropic_api_key:
        return AnthropicProvider(s.anthropic_api_key.get_secret_value(), model)
    raise SystemExit(f"provider {spec!r} is not available (ANTHROPIC_API_KEY?)")


async def run(dataset: str, specs: list[str], lang: str, limit: int | None = None) -> str:
    packs = load(dataset)[:limit]
    summary, samples = [], []
    for spec in specs:
        llm = provider(spec)
        valid = grounded = 0
        times: list[float] = []
        for event_id, pack in packs:
            system, user, srcs = brief_prompt(pack, lang)
            t0 = time.monotonic()
            try:
                raw = await llm.complete_json(system, user, EventBrief)
            except LlmError:
                samples.append((spec, event_id, pack.title, "❌ invalid JSON"))
                continue
            times.append(time.monotonic() - t0)
            valid += 1
            b = ground(raw, srcs)
            if b is None:
                samples.append((spec, event_id, pack.title, "❌ no valid source_refs"))
                continue
            grounded += 1
            samples.append((spec, event_id, pack.title, render_tg(b, srcs, lang, None)))
            print(f"{spec}: {event_id} {times[-1]:.1f}s")
        n = len(packs)
        p95 = sorted(times)[int(0.95 * (len(times) - 1))] if times else 0
        summary.append(
            f"| {spec} | {valid}/{n} | {grounded}/{n} | "
            f"{statistics.mean(times) if times else 0:.1f} | {p95:.1f} |"
        )
    lines = [
        f"# Брифы: сравнение моделей ({SystemClock().now():%Y-%m-%d}, язык {lang}, {len(packs)} событий)",
        "",
        "| Модель | Валидный JSON | С опорой на источники | Среднее, с | p95, с |",
        "|---|---|---|---|---|",
        *summary,
        "",
        "Ручная оценка: для каждого брифа поставьте 1–5 за перевод и 1–5 за полезность «Влияние/Что делать».",
        "",
    ]
    for spec, event_id, title, body in samples:
        lines += [
            f"## {spec} · {title}",
            f"`{event_id}`",
            "",
            "```html",
            body,
            "```",
            "Оценка: перевод _/5, польза _/5",
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("dataset")
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--lang", default="ru")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    report = asyncio.run(run(a.dataset, a.models, a.lang, a.limit))
    out = a.out or f"../evals/reports/{SystemClock().now():%Y-%m-%d}_briefs_v1_{a.lang}.md"
    Path(out).write_text(report, encoding="utf-8")
    print(f"→ {out}")
