# Evals обогащения: enrich_v1, режим rules

Дата: 2026-10-08

| Метрика | Значение | Цель |
|---|---|---|
| n | 60 |  |
| accuracy_sport | 1.000 | ≥ 0.9 |
| macro_f1_relevance | 0.802 |  |
| recall_high | 0.882 | ≥ 0.8 |
| precision_high | 0.714 |  |
| entities_precision | 0.914 |  |
| entities_recall | 0.987 |  |
| accuracy_rumor | 0.967 |  |

**Итог:** цели достигнуты

## Ошибки

- São Paulo acerta renovação do goleiro até o fim de 2027 — gold football/MEDIUM, got football/LOW (rules: clube da Série A(+1))
- Franca vence o Flamengo e abre vantagem na final do NBB — gold basketball/MEDIUM, got basketball/HIGH (rules: decisão(+6), resultado(+2), NBB(+1))
- Bortoleto termina o GP do Brasil de Fórmula 1 em oitavo e marca pontos — gold formula1/HIGH, got formula1/MEDIUM (rules: resultado(+2), Fórmula 1(+2))
- Bia Haddad desiste do torneio da WTA por dores no punho — gold tennis/MEDIUM, got tennis/LOW (rules: WTA(+1))
- Fortaleza vence o Ceará no Clássico-Rei e se afasta do rebaixamento — gold football/MEDIUM, got football/HIGH (rules: decisão(+6), resultado(+2), jogo próximo(+2))
- Botafogo divulga relacionados com retorno de meia após lesão — gold football/MEDIUM, got football/HIGH (rules: lesão(+6), escalação(+4), clube da Série A(+1))
- Corinthians tem dívida renegociada e torcida protesta no CT — gold football/MEDIUM, got football/LOW (rules: clube da Série A(+1))
- Ex-jogador da Seleção abre restaurante em São Paulo — gold football/LOW, got football/MEDIUM (rules: Seleção Brasileira(+2), clube da Série A(+1))
- Flamengo encaminha venda de joia da base ao futebol inglês — gold football/HIGH, got football/MEDIUM (rules: transferência(+2), clube da Série A(+1))
- Palmeiras treina com portões fechados antes do jogo da Copa do Brasil — gold football/LOW, got football/MEDIUM (rules: Copa do Brasil(+2), clube da Série A(+1))
- Juventude anuncia novo técnico após demissão no fim de semana — gold football/MEDIUM, got football/HIGH (rules: técnico(+6), Brasileirão Série A(+2))
- Sport Recife é goleado e torcida pede saída do presidente — gold football/MEDIUM, got football/LOW (rules: Brasileirão Série A(+2))
- Bahia acerta empréstimo de meia ao futebol árabe — gold football/LOW, got football/MEDIUM (rules: transferência(+4), clube da Série A(+1))
- Santos tem três desfalques por suspensão contra o Vitória — gold football/MEDIUM, got football/HIGH (rules: suspensão(+6), escalação(+2), clube da Série A(+1))
- Ingressos para final da Copa do Brasil esgotam em duas horas — gold football/LOW, got football/HIGH (rules: decisão(+6), Copa do Brasil(+2))
