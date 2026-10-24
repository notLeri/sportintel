"""Детерминированная сборка Telegram HTML и дисклеймеров (BE-T3.9)."""

import html

from sportintel.modules.editorial.domain.draft_output import DraftOutput
from sportintel.modules.editorial.domain.values import DisclaimerKind


def _bold_once(text: str, phrases: list[str]) -> str:
    """Экранированный текст, первое вхождение каждой фразы — в <b>."""
    out = html.escape(text, quote=False)
    for p in phrases:
        e = html.escape(p, quote=False)
        i = out.find(e)
        if i >= 0 and not out[:i].endswith("<b>"):
            out = f"{out[:i]}<b>{e}</b>{out[i + len(e) :]}"
    return out


def assemble(out: DraftOutput, source_link: tuple[str, str] | None) -> str:
    head = f"{out.emoji} {out.headline}" if out.emoji else out.headline
    parts = [
        f"<b>{html.escape(head, quote=False)}</b>",
        *(_bold_once(p, out.bold_phrases) for p in out.paragraphs),
    ]
    if out.hashtags:
        parts.append(" ".join(out.hashtags))
    if source_link:
        name, url = source_link
        parts.append(f'<a href="{html.escape(url)}">{html.escape(name, quote=False)}</a>')
    return "\n\n".join(parts)


def disclaimer_kinds(reliability: str, has_open_conflicts: bool) -> list[DisclaimerKind]:
    kinds = []
    if reliability in {"MEDIUM", "LOW", "UNKNOWN"}:
        kinds.append(DisclaimerKind.UNCONFIRMED)
    if has_open_conflicts:
        kinds.append(DisclaimerKind.CONFLICTING)
    return kinds
