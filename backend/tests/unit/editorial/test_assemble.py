import uuid
from types import SimpleNamespace as NS

import pytest

from sportintel.modules.editorial.domain.assemble import assemble, disclaimer_kinds
from sportintel.modules.editorial.domain.draft_output import DraftOutput, clean
from sportintel.modules.editorial.domain.template import build, cut_words, hashtag
from sportintel.modules.editorial.domain.tg_html import sanitize_tg_html
from sportintel.platform.settings_store import Drafts


def test_assemble_escapes_bold_once_hashtags_and_link() -> None:
    out = DraftOutput(
        headline="Flamengo <vence>",
        paragraphs=["Pedro marca <script>x</script> e Pedro comemora [1]"],
        emoji="⚽",
        bold_phrases=["Pedro"],
        hashtags=["#Flamengo"],
    )
    body = assemble(out, ("ge", "https://ge.globo.com/a?b=1&c=2"))
    assert body.startswith("<b>⚽ Flamengo &lt;vence&gt;</b>\n\n<b>Pedro</b> marca &lt;script&gt;")
    assert body.count("<b>Pedro</b>") == 1
    assert "#Flamengo" in body
    assert body.endswith('<a href="https://ge.globo.com/a?b=1&amp;c=2">ge</a>')
    assert sanitize_tg_html(body) == body


@pytest.mark.parametrize(
    ("rel", "conf", "kinds"),
    [
        ("HIGH", False, []),
        ("HIGH", True, ["conflicting"]),
        ("MEDIUM", False, ["unconfirmed"]),
        ("LOW", True, ["unconfirmed", "conflicting"]),
        ("UNKNOWN", False, ["unconfirmed"]),
    ],
)
def test_disclaimers(rel: str, conf: bool, kinds: list[str]) -> None:
    assert disclaimer_kinds(rel, conf) == kinds


def test_clean_drops_bad_hashtags_and_missing_bold() -> None:
    out = clean(
        DraftOutput(
            headline="h",
            paragraphs=["abc"],
            bold_phrases=["abc", "zzz"],
            hashtags=["#ok_1", "bad", "#a", "#ok_1"],
        ),
        4,
    )
    assert (out.bold_phrases, out.hashtags) == (["abc"], ["#ok_1"])


def test_template_build() -> None:
    def src(name: str, tier: str, lead: str | None) -> NS:
        return NS(
            article_id=uuid.uuid4(),
            source_name=name,
            tier=tier,
            url=f"https://{name}.example/x",
            lead=lead,
            title=f"T {name}",
        )

    pack = NS(
        sources=[
            src("cbf", "OFFICIAL", "Pedro foi cortado. Exames confirmaram lesão."),
            src("ge", "A", None),
            src("uol", "A", None),
        ],
        title="Pedro é cortado da Seleção " + "muito " * 30,
        known_names=["Pedro", "Seleção Brasileira"],
        sport_id="football",
        competition_name="Eliminatórias da Copa",
        team_names=["Vasco da Gama"],
    )
    r = build(pack, Drafts())
    assert r is not None
    o = r.output
    assert o.emoji == "⚽"
    assert len(o.headline) <= 120
    assert o.headline.endswith("…")
    assert o.paragraphs == [
        "Pedro foi cortado. Exames confirmaram lesão. [1]",
        "Also reported by: ge, uol.",
    ]
    assert (o.bold_phrases, o.hashtags) == (["Pedro"], ["#EliminatóriasDaCopa", "#VascoDaGama"])
    assert r.source_link == ("cbf", "https://cbf.example/x")
    assert r.main_article_id == pack.sources[0].article_id
    assert build(NS(sources=[]), Drafts()) is None


def test_helpers() -> None:
    assert cut_words("um dois três", 8) == "um dois…"
    assert hashtag("São Paulo FC") == "#SãoPauloFC"


def test_template_post_language_is_the_article_language() -> None:
    from sportintel.modules.editorial.domain.template import content_language

    assert content_language("ru", "en") == "ru"
    assert content_language("pt-PT", "en") == "pt-BR"
    assert content_language("es", "en") == "es"  # не притворяться языком канала
    assert content_language(None, "en") == "en"
