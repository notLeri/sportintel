import random
from pathlib import Path

import pytest

from sportintel.modules.ingestion.domain.simhash import SYNDICATION_MAX_HAMMING, hamming, simhash64
from sportintel.modules.ingestion.infrastructure.extractor import extract

PAGES = Path(__file__).resolve().parents[3].parent / "fixtures" / "sources" / "default" / "pages"

WORDS = [
    "flamengo",
    "palmeiras",
    "corinthians",
    "gremio",
    "lesao",
    "treino",
    "jogador",
    "tecnico",
    "rodada",
    "campeonato",
    "estadio",
    "torcida",
    "contrato",
    "atacante",
    "zagueiro",
    "goleiro",
    "partida",
    "vitoria",
]


def article(seed: int, sentences: int = 30) -> list[str]:
    rnd = random.Random(seed)  # noqa: S311
    return [
        " ".join(rnd.choice(WORDS) + str(rnd.randint(0, 99)) for _ in range(10)) + "."
        for _ in range(sentences)
    ]


def test_identical_texts_distance_zero() -> None:
    text = " ".join(article(1))
    a, b = simhash64(text), simhash64(text)
    assert a is not None
    assert hamming(a, b) == 0  # type: ignore[arg-type]


def test_one_sentence_changed_is_close() -> None:
    base = article(2)
    changed = [*base[:15], " ".join(article(99, 1)), *base[16:]]
    a, b = simhash64(" ".join(base)), simhash64(" ".join(changed))
    assert a is not None
    assert b is not None
    assert hamming(a, b) <= SYNDICATION_MAX_HAMMING


def test_different_articles_are_far() -> None:
    a, b = simhash64(" ".join(article(3))), simhash64(" ".join(article(4)))
    assert a is not None
    assert b is not None
    assert hamming(a, b) > 10


def test_short_text_has_no_hash() -> None:
    assert simhash64("Flamengo vence o clássico no Maracanã com gol no fim") is None


def test_signed_int64_range() -> None:
    for seed in range(20):
        h = simhash64(" ".join(article(seed)))
        assert h is not None
        assert -(2**63) <= h < 2**63


def _real(name: str) -> str:
    text = extract((PAGES / name).read_bytes(), "https://example.com/").text
    assert text
    return text


@pytest.mark.parametrize("name", ["ge_article.html", "ge_article_2.html", "cnn_article.html"])
def test_real_syndication_edits_stay_within_threshold(name: str) -> None:
    text = _real(name)
    base = simhash64(text)
    assert base is not None
    words = text.split()
    edits = [
        " ".join([*words[:10], "Estadão", *words[11:]]),
        text + " Com informações da Agência Estado.",
    ]
    for edited in edits:
        h = simhash64(edited)
        assert h is not None
        assert hamming(base, h) <= SYNDICATION_MAX_HAMMING


def test_real_different_articles_are_far() -> None:
    hashes = [
        simhash64(_real(n)) for n in ("ge_article.html", "ge_article_2.html", "cnn_article.html")
    ]
    assert all(h is not None for h in hashes)
    pairs = [(a, b) for i, a in enumerate(hashes) for b in hashes[i + 1 :]]
    assert min(hamming(a, b) for a, b in pairs) > 4 * SYNDICATION_MAX_HAMMING  # type: ignore[arg-type]
