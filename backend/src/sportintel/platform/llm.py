"""LLM-провайдеры (ADR-004): локальная Ollama — приоритет, Anthropic — опционально.

Контракт один: системный промпт + текст пользователя → экземпляр pydantic-схемы.
Ответ всегда валидируется схемой; один повтор при невалидном JSON.
"""

import asyncio
from typing import Any, Protocol, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from sportintel.platform.config import Settings
from sportintel.platform.jobs import TransientError

T = TypeVar("T", bound=BaseModel)
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MAX_TOKENS = 2048


class LlmError(Exception):
    """Модель ответила не по схеме дважды — шаг завершается ошибкой, а не мусором."""


class LlmProvider(Protocol):
    name: str
    model: str

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T: ...


async def _validated[M: BaseModel](call: Any, schema: type[M]) -> M:
    """Повтор один раз: локальные модели изредка обрывают JSON."""
    last: Exception | None = None
    for _ in range(2):
        raw = await call()
        try:
            return (
                schema.model_validate_json(raw)
                if isinstance(raw, str)
                else schema.model_validate(raw)
            )
        except ValidationError as e:
            last = e
    raise LlmError(f"invalid {schema.__name__} after retry: {last}")


class OllamaProvider:
    name = "ollama"

    def __init__(self, url: str, model: str, timeout_s: int, concurrency: int) -> None:
        self.url, self.model, self.timeout = url.rstrip("/"), model, timeout_s
        self._sem = asyncio.Semaphore(concurrency)  # локальная модель — один запрос за раз

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        body = {
            "model": self.model,
            "stream": False,
            "format": schema.model_json_schema(),  # constrained decoding по схеме
            "options": {"temperature": 0},
            "think": False,  # qwen3: без рассуждений — быстрее, JSON сразу
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }

        async def call() -> str:
            async with self._sem, httpx.AsyncClient(timeout=self.timeout) as c:
                try:
                    r = await c.post(f"{self.url}/api/chat", json=body)
                except httpx.HTTPError as e:
                    raise TransientError(f"ollama unavailable: {e}") from e
            if r.status_code >= 500:
                raise TransientError(f"ollama {r.status_code}")
            r.raise_for_status()
            return str(r.json()["message"]["content"])

        return await _validated(call, schema)


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str, timeout_s: int = 120) -> None:
        self.model, self._key, self.timeout = model, api_key, timeout_s

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        # JSON через обязательный вызов инструмента: аргументы инструмента = наша схема.
        body = {
            "model": self.model,
            "max_tokens": MAX_TOKENS,
            "temperature": 0,
            "system": system,
            "tools": [
                {
                    "name": "submit",
                    "description": "Return the result",
                    "input_schema": schema.model_json_schema(),
                }
            ],
            "tool_choice": {"type": "tool", "name": "submit"},
            "messages": [{"role": "user", "content": user}],
        }
        headers = {"x-api-key": self._key, "anthropic-version": ANTHROPIC_VERSION}

        async def call() -> dict[str, Any]:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                try:
                    r = await c.post(ANTHROPIC_URL, json=body, headers=headers)
                except httpx.HTTPError as e:
                    raise TransientError(f"anthropic unavailable: {e}") from e
            if r.status_code in (429, 529) or r.status_code >= 500:
                raise TransientError(f"anthropic {r.status_code}")
            r.raise_for_status()
            block = next(b for b in r.json()["content"] if b["type"] == "tool_use")
            return dict(block["input"])

        return await _validated(call, schema)


class FakeProvider:
    """AI_PROVIDER=fake: детерминированный ответ из фикстуры (тесты, e2e)."""

    name = "fake"
    model = "fake"

    def __init__(self, answers: dict[str, dict[str, Any]] | None = None) -> None:
        self.answers = answers or {}
        self.calls: list[tuple[str, str]] = []

    async def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        self.calls.append((system, user))
        return schema.model_validate(self.answers.get(schema.__name__, {}))


_providers: dict[tuple[str, str], LlmProvider] = {}


def make_provider(settings: Settings, model: str) -> LlmProvider | None:
    """None — AI_PROVIDER=none: шаги работают на правилах и шаблонах.

    Экземпляр кэшируется: семафор Ollama должен быть общим на процесс."""
    key = (settings.ai_provider, model)
    if key in _providers:
        return _providers[key]
    p: LlmProvider | None = None
    if settings.ai_provider == "ollama":
        p = OllamaProvider(
            settings.ollama_url, model, settings.ollama_timeout_s, settings.ollama_concurrency
        )
    elif settings.ai_provider == "anthropic" and settings.anthropic_api_key:
        p = AnthropicProvider(
            settings.anthropic_api_key.get_secret_value(), settings.anthropic_model
        )
    elif settings.ai_provider == "fake":
        p = FakeProvider()
    if p is not None:
        _providers[key] = p
    return p
