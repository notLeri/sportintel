from types import SimpleNamespace as NS

from sportintel.modules.editorial.application.post_ai import (
    AiPost,
    ai_post,
    example_markup,
    post_prompt,
)
from sportintel.modules.editorial.domain.tg_html import sanitize_tg_html
from sportintel.platform.settings_store import Drafts

SRC = [
    NS(
        source_name="ge", title="Pedro cortado", lead="Lesão.", url="https://ge.globo.com/a?x=1&y=2"
    ),
    NS(source_name="CNN", title="Pedro fora", lead="", url="https://cnn.com/b"),
]
PACK = NS(title="Pedro", sources=SRC, sport_id="football", competition_name="Brasileirão",
          team_names=["Flamengo"])  # fmt: skip


class FakeLlm:
    def __init__(self, out: AiPost) -> None:
        self.out, self.system = out, ""

    async def complete_json(self, system: str, user: str, schema: type) -> AiPost:
        self.system = system
        return self.out


def test_example_becomes_model_markup() -> None:
    ex = '⚽ <b>Head</b>\n\nAs <a href="https://a">ge reports</a>, <b>Pedro</b> &amp; co.'
    assert example_markup(ex) == "⚽ **Head**\n\nAs [ge reports](1), **Pedro** & co."


async def test_post_follows_format_and_links_come_only_from_sources() -> None:
    cfg = Drafts(post_example='<a href="https://x">per ge</a>', post_instructions="Be brief")
    llm = FakeLlm(
        AiPost(
            headline="Pedro <out>",
            body="As [ge reported](1), **Pedro** is out.\n\nSee [this](9) and [that](2).",
        )
    )
    body = await ai_post(PACK, "en", cfg, llm)
    assert body is not None
    assert "[per ge](1)" in llm.system
    assert "Be brief" in llm.system
    assert body.startswith(
        '<b>⚽ Pedro &lt;out&gt;</b>\n\nAs <a href="https://ge.globo.com/a?x=1&amp;y=2">'
    )
    assert 'See this and <a href="https://cnn.com/b">that</a>.' in body  # [9] нет — без ссылки
    assert "#Brasileirão #Flamengo" in body
    assert sanitize_tg_html(body) == body


async def test_toggles_drop_emoji_hashtags_and_links() -> None:
    cfg = Drafts(include_emoji=False, max_hashtags=0, inline_links=False,
                 include_source_link=False)  # fmt: skip
    body = await ai_post(PACK, "en", cfg, FakeLlm(AiPost(headline="H", body="[x](1) y")))
    assert body == "<b>H</b>\n\nx y"
    assert "No links" in post_prompt(PACK, "en", cfg)[0]
