import pytest
from hypothesis import given
from hypothesis import strategies as st

from sportintel.modules.ingestion.domain.url import canonicalize

CASES = [
    (
        "https://ge.globo.com/futebol/times/flamengo/noticia/2026/10/07/x.ghtml?utm_source=twitter&utm_medium=social",
        "https://ge.globo.com/futebol/times/flamengo/noticia/2026/10/07/x.ghtml",
    ),
    (
        "https://ge.globo.com/futebol/noticia/2026/10/07/x.ghtml#comentarios",
        "https://ge.globo.com/futebol/noticia/2026/10/07/x.ghtml",
    ),
    ("HTTPS://GE.Globo.COM:443/Futebol/", "https://ge.globo.com/Futebol"),
    (
        "https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/07/x.htm?cmpid=copiaecola",
        "https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/07/x.htm",
    ),
    (
        "https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/07/x.amp.htm",
        "https://www.uol.com.br/esporte/futebol/ultimas-noticias/2026/10/07/x.amp.htm",
    ),
    (
        "https://www.espn.com.br/futebol/artigo/_/id/1234/x?ref=homepage&fbclid=abc",
        "https://www.espn.com.br/futebol/artigo/_/id/1234/x",
    ),
    ("https://www.lance.com.br/flamengo/x.html/amp", "https://www.lance.com.br/flamengo/x.html"),
    ("https://www.lance.com.br/amp/flamengo/x.html", "https://www.lance.com.br/flamengo/x.html"),
    ("https://www.lance.com.br/flamengo/x.amp", "https://www.lance.com.br/flamengo/x"),
    ("https://www.lance.com.br//flamengo///x.html", "https://www.lance.com.br/flamengo/x.html"),
    ("http://www.lance.com.br:80/x?gclid=1", "http://www.lance.com.br/x"),
    ("https://example.com:8443/x", "https://example.com:8443/x"),
    ("https://ge.globo.com", "https://ge.globo.com/"),
    ("https://ge.globo.com/?page=2", "https://ge.globo.com/"),
    ("https://ge.globo.com/São-Paulo/notícia", "https://ge.globo.com/S%C3%A3o-Paulo/not%C3%ADcia"),
    ("https://ge.globo.com/S%c3%a3o-Paulo", "https://ge.globo.com/S%C3%A3o-Paulo"),
    ("https://ge.globo.com/%7Euser/%41bc", "https://ge.globo.com/~user/Abc"),
    ("https://ge.globo.com/a%2Fb", "https://ge.globo.com/a%2Fb"),
    (
        "https://пример.рф/новость",
        "https://xn--e1afmkfd.xn--p1ai/%D0%BD%D0%BE%D0%B2%D0%BE%D1%81%D1%82%D1%8C",
    ),
    (
        "  https://ge.globo.com/x?outputType=amp&__twitter_impression=true  ",
        "https://ge.globo.com/x",
    ),
    (
        "https://cnnbrasil.com.br/esportes/x/?utm_campaign=a&mc_cid=b&mc_eid=c&ref_src=d",
        "https://cnnbrasil.com.br/esportes/x",
    ),
    ("https://user:pass@ge.globo.com/x", "https://ge.globo.com/x"),
]


@pytest.mark.parametrize(("raw", "expected"), CASES)
def test_canonicalize(raw: str, expected: str) -> None:
    assert canonicalize(raw) == expected


def test_same_article_different_utm_one_canonical() -> None:
    a = canonicalize("https://ge.globo.com/x.ghtml?utm_source=a")
    b = canonicalize("https://ge.globo.com/x.ghtml?utm_source=b&utm_medium=c#top")
    assert a == b


def test_keep_params_preserved_and_sorted() -> None:
    url = "https://cbf.com.br/noticia?id=5&page=2&ano=2026&utm_source=x"
    assert (
        canonicalize(url, frozenset({"id", "ano", "utm_source"}))
        == "https://cbf.com.br/noticia?ano=2026&id=5"
    )


@pytest.mark.parametrize(
    "bad",
    [
        "ge.globo.com/x",
        "ftp://ge.globo.com/x",
        "javascript:alert(1)",
        "https://",
        "https://ge.globo.com:99999/",
    ],
)
def test_invalid(bad: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — сообщение не часть контракта
        canonicalize(bad)


_segment = st.text(alphabet=st.characters(blacklist_categories=("Cs", "Cc")), max_size=12)


@given(
    scheme=st.sampled_from(["http", "https"]),
    host=st.from_regex(r"[a-z]{1,10}(\.[a-z]{2,6}){1,2}", fullmatch=True),
    segments=st.lists(_segment, max_size=5),
    params=st.dictionaries(
        st.sampled_from(["id", "utm_source", "page", "q"]), st.text(max_size=5), max_size=3
    ),
)
def test_idempotent(scheme: str, host: str, segments: list[str], params: dict[str, str]) -> None:
    from urllib.parse import quote, urlencode

    url = f"{scheme}://{host}/" + "/".join(quote(s, safe="") for s in segments)
    if params:
        url += "?" + urlencode(params)
    once = canonicalize(url, frozenset({"id", "q"}))
    assert canonicalize(once, frozenset({"id", "q"})) == once
