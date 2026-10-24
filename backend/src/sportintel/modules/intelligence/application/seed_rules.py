"""Seed `enrich_rules` (ADR-004): рубрика iGaming из BE-T2.7, переложенная в правила с весами.

Веса откалиброваны на таблице заголовков tests/integration/intelligence/test_rule_enrich.py.
"""

# fmt: off
SEED_ENRICH_RULES = {
    "sport_url_patterns": {
        "football": ["/futebol/", "/futebol-", "/brasileirao", "/libertadores", "/copa-do-brasil", "/selecao-brasileira"],
        "basketball": ["/basquete/", "/nba/", "/nbb/"],
        "tennis": ["/tenis/"],
        "mma": ["/mma/", "/ufc/", "/combate/"],
        "formula1": ["/formula-1/", "/f1/", "/automobilismo/"],
        "volleyball": ["/volei/"],
    },
    "sport_keywords": {
        "football": ["futebol", "gol", "zagueiro", "atacante", "goleiro", "volante", "escalação", "pênalti", "escanteio"],
        "basketball": ["basquete", "armador", "pivô", "rebote", "NBA", "NBB"],
        "tennis": ["tênis", "tenista", "raquete", "ATP", "WTA", "Grand Slam"],
        "mma": ["MMA", "UFC", "octógono", "nocaute", "cinturão"],
        "formula1": ["Fórmula 1", "F1", "pole position", "pit stop", "grid de largada", "escuderia"],
        "volleyball": ["vôlei", "Superliga", "levantador", "levantadora", "ponteiro", "líbero"],
    },
    # Омонимы (канонические имена): обычное слово («Internacional», «Juventude», «Remo»), город или штат
    # («São Paulo», «Santos», «Bahia»), короткий алиас («Sport», «América»). Нужен второй сигнал.
    "ambiguous_entities": ["Internacional", "São Paulo", "Santos", "Bahia", "Vitória", "Remo", "Sport Recife", "Juventude", "Fortaleza", "Ceará", "Goiás", "Cuiabá", "Londrina", "Criciúma", "Mirassol", "América Mineiro", "Náutico"],
    "sports_domains": ["t.me", "calend.ru", "officeholidays.com", "openholidaysapi.org", "www.gov.uk", "brasilapi.com.br", "ru.wikipedia.org"],  # t.me — профильные каналы; остальное — календари праздников
    "rss_category_map": {"futebol": "football", "basquete": "basketball", "tenis": "tennis", "volei": "volleyball", "mma": "mma", "formula 1": "formula1"},
    "relevance_rules": [
        {"name": "Травма", "weight": 3, "words": {"pt-BR": ["lesão", "lesões", "lesionado", "contusão", "desfalque", "desfalca", "departamento médico", "cirurgia", "vetado", "dúvida para"], "en": ["injury", "injured"], "ru": ["травма", "травмы", "травму", "травмирован", "пропустит"]}},
        {"name": "Дисквалификация", "weight": 3, "words": {"pt-BR": ["suspenso", "suspende", "suspensão", "cartão vermelho", "expulso", "STJD", "julgamento", "punição", "punido", "pendurado", "perde posições"], "en": ["suspended", "suspension", "red card"], "ru": ["дисквалификация", "дисквалифицирован", "удаление", "красная карточка"]}},
        {"name": "Состав на матч", "weight": 2, "words": {"pt-BR": ["escalação", "escalado", "titular", "titulares", "poupado", "relacionados", "provável time", "time titular"]}},
        {"name": "Смена тренера", "weight": 3, "words": {"pt-BR": ["demite", "demitiu", "demitido", "demissão", "novo técnico", "novo treinador", "interino", "deixa o cargo", "anuncia técnico", "saída de técnico", "saída do técnico", "balança no cargo"], "en": ["sacked", "fired", "new coach", "new manager"], "ru": ["уволен", "отставка", "новый тренер", "главный тренер"]}},
        {"name": "Перенос или условия матча", "weight": 3, "words": {"pt-BR": ["adiado", "adiamento", "mudança de local", "jogará com portões fechados", "sem torcida", "sem público", "condições do gramado", "chuva forte"]}},
        {"name": "Решающий матч", "weight": 3, "words": {"pt-BR": ["final da", "na final", "a final", "semifinal", "campeão", "conquista o", "conquista a", "elimina", "eliminado", "eliminação", "rebaixamento", "rebaixado"], "en": ["final", "champion", "relegated"], "ru": ["финал", "финале", "чемпион", "чемпионом", "вылет"]}},
        {"name": "Вызов в сборную", "weight": 3, "words": {"pt-BR": ["convoca", "convocação", "convocado", "convocada", "convocados"]}},
        {"name": "Допинг", "weight": 3, "words": {"pt-BR": ["doping", "antidoping"]}},
        {"name": "Трансфер", "weight": 2, "words": {"pt-BR": ["contratação", "contratado", "reforço", "negociação", "proposta", "transferência", "empréstimo", "acerta com", "assina com", "interesse em", "sondagem", "sondado", "na mira"], "en": ["transfer", "signs", "signed"], "ru": ["трансфер", "подписал", "переход", "перешел"]}},
        {"name": "Результат", "weight": 1, "words": {"pt-BR": ["vence", "venceu", "derrota", "empata", "empate", "goleada", "classificação", "rodada", "placar", "pódio", "pole position", "marca pontos"], "en": ["wins", "beat", "beats"], "ru": ["победа", "победил", "поражение", "ничья", "счет"]}},
        {"name": "Ближайший матч", "weight": 1, "words": {"pt-BR": ["hoje", "amanhã", "clássico"]}},
        {"name": "Главный бой", "weight": 1, "words": {"pt-BR": ["card principal", "luta principal", "cinturão", "disputa de título"]}},
        {"name": "Вне поля", "weight": -1, "words": {"pt-BR": ["patrocínio", "patrocinador", "balanço financeiro", "eleição", "sócio-torcedor", "homenagem", "camisa nova", "uniforme"]}},
        {"name": "Регулирование", "weight": 3, "words": {"en": ["license", "licence", "ban", "fine", "regulator", "law", "tax"], "ru": ["лицензия", "лицензии", "запрет", "штраф", "регулятор", "закон", "законопроект", "налог"]}},
        {"name": "Праздник", "weight": 2, "words": {"en": ["holiday", "public holiday", "national day", "independence day", "world day", "international day"], "ru": ["праздник", "всемирный день", "международный день", "день независимости", "выходной день"]}},
    ],
    "competition_weight": {},
    "level_thresholds": {"HIGH": 6, "MEDIUM": 3, "LOW": 1},
    "body_weight": 0.5,  # прогон 2026-10-09: при 1.0 HIGH получали 57% статей ge, при 0.5 — 36%
    "rumor_markers": {"pt-BR": ["segundo apuração", "especula-se", "especulado", "interesse", "negocia", "sondagem", "nos bastidores", "de acordo com fontes", "estaria", "teria", "rumor", "boato"]},
    "clickbait_patterns": [r"(?i)você não vai acreditar", r"(?i)\bveja (o que|como|quem)\b", r"(?i)\bsaiba (o que|quem|qual)\b", r"!{2,}", r"(?i)\bchocante\b"],
    "version": 5,
}

# Источники на en/ru (Telegram-каналы, праздники) — 2026-10-10. Слова — целиком (\b), без морфологии:
# частые словоформы перечислены явно.
_EN_RU = {
    "sport_url_patterns": {
        "holidays": ["/holidays/", "/publicholidays", "/bank-holidays", "/feriados/",
                     "/wiki/%d0%9f%d1%80%d0%b0%d0%b7%d0%b4%d0%bd%d0%b8%d0%ba%d0%b8_"],  # «Праздники_…» в Википедии
        "football": ["/football/"],
        "igaming": ["/igaming_news/", "/dailyigamingen/"],  # профильные Telegram-каналы целиком
    },
    "sport_keywords": {
        "football": ["football", "soccer", "футбол", "футболист", "Premier League", "Champions League", "РПЛ", "АПЛ", "Лига чемпионов", "вратарь", "goalkeeper"],
        "basketball": ["basketball", "баскетбол", "НБА", "Евролига", "EuroLeague"],
        "tennis": ["tennis", "теннис", "теннисист", "теннисистка"],
        "mma": ["knockout", "нокаут", "бой", "боец"],
        "formula1": ["Formula 1", "Формула-1", "Grand Prix", "Гран-при"],
        "volleyball": ["volleyball", "волейбол"],
        "hockey": ["hockey", "хоккей", "хоккеист", "КХЛ", "NHL", "НХЛ", "шайба"],
        "igaming": ["casino", "казино", "iGaming", "gambling", "гемблинг", "betting", "беттинг", "букмекер", "букмекеры", "bookmaker", "sportsbook", "slots", "слоты", "lottery", "лотерея", "prediction market", "рынок прогнозов", "рынков прогнозов"],
    },
    "sports_domains": ["t.me", "calend.ru", "officeholidays.com", "en.wikipedia.org"],  # wikipedia — только страницы праздников  # t.me: подключаем только профильные каналы
}
for _k, _v in _EN_RU.items():
    if isinstance(_v, dict):
        for _sport, _items in _v.items():
            SEED_ENRICH_RULES[_k].setdefault(_sport, []).extend(_items)  # type: ignore[attr-defined]
    else:
        SEED_ENRICH_RULES[_k].extend(_v)  # type: ignore[attr-defined]
# fmt: on
