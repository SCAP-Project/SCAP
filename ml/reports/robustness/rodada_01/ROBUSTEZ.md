# Auditoria e robustez — anomalias de valor

**Conclusão:** os números altos se repetem dentro do gerador original, mas o desempenho não se sustenta nos desafios mais difíceis. O experimento inicial mede uma tarefa sintética favorável; não demonstra robustez operacional.

## Auditoria do experimento original

Foram verificados histórico por filtros independentes em 150 transações, atributos proibidos, mutação de dados futuros, períodos/IDs, cópias exatas de negócios, estatísticas do scaler e reprodução de scores/métricas.
- Passou: Historicos recalculados de forma independente.
- Passou: Whitelist de atributos.
- Passou: Mutar futuro e colunas proibidas preserva passado.
- Passou: Periodos e identificadores disjuntos.
- Passou: Sem copia exata de negocios entre treino e teste.
- Passou: Scaler compativel com ajuste apenas no treino.
- Passou: Scores e metricas originais reproduzidos.

Essas verificações não encontraram vazamento direto ou erro aritmético. Não são uma prova de ausência de todo vazamento possível, nem de realismo dos dados.
No controle negativo, embaralhar os rótulos 100 vezes levou a AP média **0.0662** (mínimo 0.0613, máximo 0.0766), contra **0.9864** observada. Isso verifica associação com o rótulo; não valida a aplicação real.

## Novos conjuntos independentes

Três seeds novas (101, 202, 303), cinco cenários pareados por seed e os três modelos originais: 15 datasets e 45 avaliações. Cada fonte tem novos parceiros/observações. Pesos, pré-processamento e limiares ficaram congelados; nenhum resultado de desafio recalibrou o modelo.
Os históricos das novas fontes usam seus dias anteriores. Apenas o segundo semestre/2025 entra nas métricas. A nova seed testa outra realização da mesma família geradora; não representa validação externa em dados empresariais.

### Modelo escolhido originalmente: Desvio historico

Médias simples entre as três seeds; a faixa mostra mínimo e máximo, não intervalo de confiança.

| Cenário | AP média | Precisão média | Recall médio | F1 médio | Faixa de F1 | Falsos alertas entre normais |
|---|---:|---:|---:|---:|---|---:|
| Gerador original | 0.9848 | 98.64% | 95.21% | 0.9690 | 0.9587–0.9771 | 0.09% |
| Anomalias sutis | 0.4067 | 53.62% | 31.39% | 0.3958 | 0.3772–0.4221 | 1.87% |
| Extremos legítimos | 0.6343 | 58.58% | 86.76% | 0.6994 | 0.6947–0.7081 | 4.22% |
| Mudança de regime | 0.8843 | 47.72% | 92.16% | 0.6288 | 0.6178–0.6392 | 6.96% |
| Combinado | 0.0711 | 7.69% | 15.18% | 0.1020 | 0.0939–0.1107 | 12.57% |

### Como interpretar os cenários

- **Original:** mesmas regras amplas de injeção e pequena variação normal; a boa repetição mostra estabilidade dentro dessa família.
- **Sutis:** multiplicadores 1,1–1,3 ou 0,7–0,9, mantendo o conjunto de transações adulteradas. As distribuições passam a se sobrepor mais.
- **Extremos legítimos:** cerca de 5% dos registros normais recebem picos 1,5–3,5, com rótulo normal. Sem uma variável observável que explique o evento válido, alguns valores são indistinguíveis de adulterações. Este cenário explicita um limite de observabilidade do alvo, não apenas de algoritmo.
- **Mudança de regime:** 30% dos parceiros passam a operar em nível 1,8 vezes maior a partir de julho/2025, sem mudança de rótulo por esse motivo. AP pode continuar razoável enquanto o F1 cai: ranking e calibração são problemas distintos.
- **Combinado:** anomalias sutis, ruído multiplicativo legítimo extra (sigma log 0,25), picos legítimos e regime novo. É um stress test construído, não uma estimativa da frequência desses eventos em empresas reais.
Os rótulos continuam significando adulteração artificial de valor, enquanto eventos legítimos podem ser estatisticamente atípicos. Para separar legitimidade de adulteração, pode ser necessário contexto operacional que esse dataset não contém.

## Retirada de grupos de atributos

As ablações são diagnósticos no dataset original já inspecionado. Cada variante ajustou o pré-processador/modelo só no treino e o limiar só na validação; as variantes não substituíram o selecionado original.
A chave interna `so_historico` corresponde a **Desvios atuais + histórico**: inclui o desvio do valor da transação atual em relação ao passado. Não é um modelo que observa apenas o passado. O controle `sem_valor_atual` retira também esses desvios derivados.

| Grupo | Modelo | AP validação | AP teste diagnóstico | F1 teste diagnóstico | Taxa de alerta |
|---|---|---:|---:|---:|---:|
| Completo | Isolation Forest | 0.7956 | 0.8296 | 0.8239 | 5.62% |
| Completo | Autoencoder | 0.2944 | 0.3515 | 0.3853 | 5.84% |
| Sem histórico | Isolation Forest | 0.0918 | 0.1014 | 0.1585 | 14.07% |
| Sem histórico | Autoencoder | 0.0811 | 0.0730 | 0.1253 | 62.81% |
| Desvios atuais + histórico | Isolation Forest | 0.8795 | 0.9240 | 0.9386 | 6.91% |
| Desvios atuais + histórico | Autoencoder | 0.5840 | 0.5027 | 0.4283 | 10.23% |
| Sem categorias | Isolation Forest | 0.8885 | 0.9135 | 0.9217 | 6.31% |
| Sem categorias | Autoencoder | 0.3864 | 0.4370 | 0.4135 | 3.95% |
| Sem calendário | Isolation Forest | 0.6731 | 0.7550 | 0.7827 | 6.23% |
| Sem calendário | Autoencoder | 0.2447 | 0.2438 | 0.2335 | 10.79% |
| Sem valor atual e derivados | Isolation Forest | 0.0638 | 0.0682 | 0.1228 | 100.00% |
| Sem valor atual e derivados | Autoencoder | 0.0590 | 0.0676 | 0.1230 | 99.81% |
| Historico completo | Regra | 0.9812 | 0.9864 | 0.9753 | 6.33% |
| Historico 90 dias | Regra | 0.9706 | 0.9769 | 0.9484 | 6.47% |
| Valor global | Regra | 0.2411 | 0.2684 | 0.3187 | 10.20% |

Retirar o histórico derruba os modelos aprendidos; retirar valor atual e todos os seus desvios deixa a AP próxima da prevalência. Recall de 100% com taxa de alerta de 100% é o comportamento trivial de alertar tudo, não um detector eficaz.
Algumas variantes com menos contexto categórico melhoram os modelos aprendidos nesta análise exploratória. Isso sugere hipóteses para outra rodada; não é motivo para promover uma variante usando o teste já observado.

## Resposta à suspeita inicial

Os números originais não parecem decorrer de um vazamento direto detectável pelas verificações realizadas. O fator principal é a separação fácil criada pelo gerador: comportamento normal estável por parceiro e alterações artificiais expressivas.
O F1 médio do modelo escolhido passa de **0.9690** no cenário original para **0.3958** nas anomalias sutis e **0.1020** no combinado. Portanto, a conclusão adequada é **bom desempenho na simulação simples, robustez insuficiente nos desafios avaliados**.

## Próximos experimentos

1. Fixar o significado operacional de anomalia: desvio estatístico, adulteração ou evento que exige revisão humana.
2. Reservar uma fonte/seed/período ainda não inspecionado antes de testar melhorias sugeridas por esta análise.
3. Comparar referências robustas e adaptação de regime usando só treino/validação; avaliar custos de falsos alertas e falta de histórico.
4. Adicionar contexto observável de eventos legítimos, se disponível, para reduzir ambiguidades do rótulo.
5. Tratar os desafios atuais como desenvolvimento/diagnóstico em futuras decisões: eles já foram observados.

## Rastreabilidade

O protocolo registra seeds, cenários, hashes dos métodos/dependências, versões, modelos/artefatos originais e configuração antes da execução. Reexecuções com método ou ambiente diferente são rejeitadas e exigem um novo `--run-id`. O registro é local, não um pré-registro externo.
As saídas originais foram preservadas e conferidas por hash. Resultados completos, predições e datasets estão em pastas separadas da rodada. Os documentos de auditoria são evidência do que foi verificado; não certificam ausência de todo erro possível.
