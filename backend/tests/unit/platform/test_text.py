import pytest

from sportintel.platform.text import normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  São   PAULO ", "sao paulo"),
        ("", ""),
        ("   ", ""),
        ("Grêmio", "gremio"),
        ("Atlético-MG", "atletico-mg"),
        ("Conceição", "conceicao"),
        ("FLAMENGO", "flamengo"),
        ("João\tPedro\n", "joao pedro"),
        ("Ñuñoa", "nunoa"),
        ("Vitória ⚽", "vitoria ⚽"),
        ("São Paulo 🇧🇷", "sao paulo 🇧🇷"),
        ("ﬁfa", "fifa"),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected
