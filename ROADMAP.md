# Roadmap — SCAP

Atualizado em 09/11/2026.

## Infraestrutura

A conta AWS foi encerrada. O projeto usa CSVs locais. SQLs e ETLs de banco
permanecem como referência histórica.

## Concluído — ETL CSV

- [x] Arquitetura raw → trusted → refined.
- [x] Geração de 24 meses de transações e gabarito separado.
- [x] Correção do parcelamento e regeneração dos parceiros derivados.
- [x] Validação e transformação das sete entidades da origem.
- [x] Seis dimensões e quatro fatos em refined.
- [x] Saldos diários por área/moeda, incluindo dias sem movimento.
- [x] Histórico diário e chaves estáveis nas reexecuções.
- [x] Executor local, manifesto com hashes, testes e documentação.

Primeira execução: 39.792 transações, 20.724 pagamentos, 18.681 recebimentos
e 15.440 saldos diários.

## Concluído — primeiro experimento de anomalias

- [x] Dez notebooks de análise exploratória, um por tabela de refined.
- [x] Objetivo: detectar anomalias de valor injetadas pelo gerador.
- [x] Atributos por parceiro/tipo usando somente dias anteriores.
- [x] Treino em 2024, validação no primeiro semestre/2025 e teste no segundo.
- [x] Baseline histórico, Isolation Forest e autoencoder.
- [x] Seleção e calibração na validação, teste final e análise de erros.
- [x] Figuras PNG/SVG, notebooks executados e relatório de resultados.

## Próximas entregas

- [x] Auditoria dos históricos, métricas, atributos e controle negativo.
- [x] Novas seeds, cenários difíceis e ablação, com modelos originais congelados.
- [ ] Reservar outro dataset/seed antes de avaliar melhorias motivadas pelos desafios.
- [ ] Avaliar generalização e variações controladas do experimento.
- [ ] Dashboard Power BI consumindo CSVs e resultados.
- [ ] CI com execução automática dos testes.
- [ ] Redação e documentação final do TCC.

## Limites conhecidos

- Dados sintéticos, com operações somente em BRL.
- Histórico de cadastro começa na observação, sem reconstrução retroativa.
- Alterações no mesmo dia consolidam a versão diária.
- Rating e prazo médio completos ficam fora do treino temporal.
- Feriados não implementados; dia útil significa segunda a sexta.
- Remoção de fatos existentes é rejeitada para evitar reutilização de chaves.
- Os três fatos adicionais foram concluídos em CSV, não no ETL PostgreSQL.
- O modelo detecta distorções artificiais de valor, não fraude comprovada.
