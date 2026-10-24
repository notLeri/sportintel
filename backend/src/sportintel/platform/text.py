import unicodedata


def normalize_name(s: str) -> str:
    """NFKD → без диакритики → lower → схлопывание пробелов → trim (CONV §6.1)."""
    decomposed = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())
