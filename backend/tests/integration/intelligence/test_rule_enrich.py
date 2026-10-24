"""Таблица реалистичных заголовков pt-BR → вид спорта и уровень важности (BE-T2.7 §17, ADR-004)."""

from datetime import UTC, datetime

import pytest

from sportintel.modules.intelligence.application.rule_enrich import enrich_with_rules
from sportintel.modules.intelligence.domain.rules import ArticleInput
from sportintel.platform import settings_store
from sportintel.platform.db import Database

GE = "https://ge.globo.com/futebol/times/x/noticia/2026/10/08/y.ghtml"
CASES = [
    # (url, title, lead, sport, level)
    (
        GE,
        "Flamengo confirma lesão de Pedro, que desfalca o time no clássico",
        "Atacante sentiu dores na coxa.",
        "football",
        "HIGH",
    ),
    (
        GE,
        "Palmeiras: Abel define escalação com titulares para a Libertadores",
        "Time deve ter força máxima.",
        "football",
        "HIGH",
    ),
    (
        GE,
        "Corinthians demite técnico após derrota no Brasileirão",
        "Diretoria anunciou a saída.",
        "football",
        "HIGH",
    ),
    (
        GE,
        "STJD suspende atacante do Vasco por quatro jogos",
        "Jogador foi expulso na última rodada.",
        "football",
        "HIGH",
    ),
    (
        GE,
        "Jogo do Grêmio é adiado por causa da chuva forte em Porto Alegre",
        None,
        "football",
        "HIGH",
    ),
    (
        GE,
        "São Paulo acerta com volante para a próxima temporada",
        "Negociação foi concluída nesta quarta.",
        "football",
        "MEDIUM",
    ),
    (
        GE,
        "Botafogo vence o Bahia e segue na briga pelo título do Brasileirão",
        "Placar de 2 a 0.",
        "football",
        "MEDIUM",
    ),
    (
        GE,
        "Santos tem interesse em lateral, segundo apuração do ge",
        "Clube fez sondagem.",
        "football",
        "MEDIUM",
    ),
    (
        GE,
        "Cruzeiro lança camisa nova com patrocinador master",
        "Uniforme será usado no clássico.",
        "football",
        "LOW",
    ),
    (
        GE,
        "Atlético-MG treina no CT com foco no próximo jogo",
        "Elenco fez atividade leve.",
        "football",
        "LOW",
    ),
    (
        "https://ge.globo.com/basquete/nbb/noticia/x.ghtml",
        "Franca vence o Flamengo na abertura do NBB",
        "Jogo equilibrado.",
        "basketball",
        "MEDIUM",
    ),
    (
        "https://ge.globo.com/volei/noticia/x.ghtml",
        "Levantadora da seleção sofre lesão e vira dúvida para a Superliga",
        None,
        "volleyball",
        "HIGH",
    ),
    (
        "https://ge.globo.com/combate/noticia/x.ghtml",
        "UFC anuncia brasileiro no card principal com cinturão em jogo",
        None,
        "mma",
        "MEDIUM",
    ),
    (
        "https://ge.globo.com/motor/formula-1/noticia/x.ghtml",
        "Fórmula 1: piloto é punido e larga do fim do grid de largada",
        None,
        "formula1",
        "HIGH",
    ),
    (
        "https://ge.globo.com/tenis/noticia/x.ghtml",
        "Tenista brasileiro vence e avança no ATP 500",
        None,
        "tennis",
        "MEDIUM",
    ),
    (
        "https://www.cnnbrasil.com.br/esportes/futebol/x/",
        "Internacional anuncia novo técnico após saída do treinador",
        None,
        "football",
        "HIGH",
    ),
    (
        "https://www.cnnbrasil.com.br/economia/x/",
        "Dólar fecha em alta após dados de inflação",
        "Mercado reagiu.",
        None,
        "IRRELEVANT",
    ),
    (
        "https://www.cnnbrasil.com.br/politica/x/",
        "Câmara aprova projeto em votação na madrugada",
        None,
        None,
        "IRRELEVANT",
    ),
    (
        GE,
        "Fluminense: veja o que disse o técnico após o empate",
        "Entrevista coletiva.",
        "football",
        "LOW",
    ),
    (
        GE,
        "Seleção Brasileira: convocação tem titular poupado e dúvida para as Eliminatórias",
        None,
        "football",
        "HIGH",
    ),
    (
        GE,
        "Mengão empata com o Timão em clássico movimentado no Maracanã",
        None,
        "football",
        "MEDIUM",
    ),
]


@pytest.mark.parametrize(("url", "title", "lead", "sport", "level"), CASES)
async def test_rules_table(
    db: Database, url: str, title: str, lead: str | None, sport: str | None, level: str
) -> None:
    settings_store.clear_cache()
    a = ArticleInput(url, title, lead, None, (), "pt-BR", datetime(2026, 10, 8, tzinfo=UTC))
    async with db.uow() as u:
        out = await enrich_with_rules(db, u, a)
    assert (out.sport, out.relevance.level.value) == (sport, level), out.relevance.rationale
    assert out.relevance.rationale.startswith("rules:")
    assert len(out.relevance.rationale) <= 280


async def test_entities_and_competition(db: Database) -> None:
    settings_store.clear_cache()
    a = ArticleInput(
        GE, "Mengão vence o Palmeiras pelo Brasileirão", "Pedro marcou.", None, (), "pt-BR", None
    )
    async with db.uow() as u:
        out = await enrich_with_rules(db, u, a)
    assert out.competition is not None
    assert out.competition.canonical_guess == "Brasileirão Série A"
    assert {(e.canonical_guess, e.role) for e in out.entities} == {
        ("Flamengo", "subject"),
        ("Palmeiras", "subject"),
    }
