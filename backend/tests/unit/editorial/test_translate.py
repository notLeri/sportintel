from contextlib import asynccontextmanager
from typing import Any

from sportintel.modules.editorial.application.translate import already_in, translate
from sportintel.platform.llm import FakeProvider


class _Db:
    @asynccontextmanager
    async def uow(self) -> Any:
        yield None


class _Cache:
    def __init__(self) -> None:
        self.rows: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.rows.get(key)

    async def put(self, key: str, lang: str, text: str, model: str) -> None:
        self.rows[key] = text


async def test_same_text_is_translated_once() -> None:
    cache, llm = _Cache(), FakeProvider({"Translation": {"text": "Палмейрас выиграл"}})
    for _ in range(2):
        out = await translate(_Db(), lambda _: cache, llm, "Palmeiras vence", "ru")  # type: ignore[arg-type]
    assert out == "Палмейрас выиграл"
    assert len(llm.calls) == 1


async def test_russian_text_is_not_sent_to_the_model() -> None:
    llm = FakeProvider()
    text = "<b>Монтелла</b> больше не тренер сборной Турции"
    assert already_in(text, "ru")
    assert await translate(_Db(), lambda _: _Cache(), llm, text, "ru", html=True) == text  # type: ignore[arg-type]
    assert llm.calls == []


async def test_event_title_and_summary_in_one_call_then_cached() -> None:
    from sportintel.modules.editorial.application.translate import translate_pair

    cache = _Cache()
    llm = FakeProvider(
        {"EventText": {"title": "«Васко» вернул Гомеса", "summary": "Андрес Гомес в составе."}}
    )
    for _ in range(2):
        out = await translate_pair(
            _Db(), lambda _: cache, llm, "Vasco tem Gómez", "Andrés Gómez volta.", "ru"
        )  # type: ignore[arg-type]
    assert out == ("«Васко» вернул Гомеса", "Андрес Гомес в составе.")
    assert len(llm.calls) == 1
