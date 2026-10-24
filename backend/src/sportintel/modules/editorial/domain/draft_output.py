"""DraftOutput — общий контракт шаблона и LM (BE-T3.9). Валидация кодом: домен без pydantic."""

import re
from dataclasses import dataclass, field, replace

HASHTAG = re.compile(r"^#[0-9A-Za-zÀ-ÿ_]{2,30}$")
HEADLINE_MAX, PARAGRAPH_MAX, MAX_PARAGRAPHS, MAX_BOLD = 120, 600, 5, 3


@dataclass(frozen=True)
class DraftOutput:
    headline: str
    paragraphs: list[str]
    emoji: str | None = None
    bold_phrases: list[str] = field(default_factory=list)
    hashtags: list[str] = field(default_factory=list)


def clean(out: DraftOutput, max_hashtags: int) -> DraftOutput:
    """Невалидные хэштеги и bold-фразы, которых нет в тексте, отбрасываются (§11)."""
    paragraphs = [p[:PARAGRAPH_MAX] for p in out.paragraphs if p.strip()][:MAX_PARAGRAPHS]
    text = "\n".join(paragraphs)
    return replace(
        out,
        emoji=(out.emoji or None) and out.emoji[:4],
        headline=out.headline[:HEADLINE_MAX],
        paragraphs=paragraphs,
        bold_phrases=[b for b in out.bold_phrases if b and b in text][:MAX_BOLD],
        hashtags=[h for h in dict.fromkeys(out.hashtags) if HASHTAG.match(h)][:max_hashtags],
    )
