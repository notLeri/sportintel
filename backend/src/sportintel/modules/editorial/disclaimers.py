"""Тексты дисклеймеров по языкам (BE-T3.7). Рендерятся над постом, в body_tg_html не входят."""

TEXTS = {
    "unconfirmed": {
        "pt-BR": "⚠️ Informação ainda não confirmada oficialmente.",
        "en": "⚠️ Not yet officially confirmed.",
        "ru": "⚠️ Информация пока официально не подтверждена.",
    },
    "conflicting": {
        "pt-BR": "⚠️ As fontes trazem informações conflitantes.",
        "en": "⚠️ Sources report conflicting information.",
        "ru": "⚠️ Источники сообщают противоречивые сведения.",
    },
}


def render(kinds: list[str], language: str) -> str | None:
    lines = [TEXTS[k].get(language, TEXTS[k]["en"]) for k in kinds if k in TEXTS]
    return "\n".join(lines) or None
