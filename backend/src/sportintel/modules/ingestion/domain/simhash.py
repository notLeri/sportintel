"""64-битный SimHash (BE-T1.7): почти-дубли → малое расстояние Хэмминга.

Шинглы по 2 слова и порог 6 выбраны измерением на реальных статьях (≈200 слов):
правка слова/приписка агентства/замена предложения дают ≤ 6, разные статьи — ≥ 30;
шинглы по 3 слова из спецификации давали до 14 на тех же правках (см. BE-T1.7, ADR-заметка).
"""

import hashlib

from sportintel.platform.text import normalize_name

MIN_WORDS = 50
SHINGLE = 2
SYNDICATION_MAX_HAMMING = 6
_MASK = (1 << 64) - 1


def simhash64(text: str) -> int | None:
    """Signed int64 (для bigint) или None — текст короче 50 слов."""
    words = [w for w in normalize_name(text).split() if len(w) >= 3]
    if len(words) < MIN_WORDS:
        return None
    weights = [0] * 64
    for i in range(len(words) - SHINGLE + 1):
        shingle = " ".join(words[i : i + SHINGLE]).encode()
        h = int.from_bytes(hashlib.blake2b(shingle, digest_size=8).digest(), "big")
        for bit in range(64):
            weights[bit] += 1 if h >> bit & 1 else -1
    value = sum(1 << bit for bit in range(64) if weights[bit] > 0)
    return value - (1 << 64) if value >= 1 << 63 else value


def hamming(a: int, b: int) -> int:
    return ((a ^ b) & _MASK).bit_count()
