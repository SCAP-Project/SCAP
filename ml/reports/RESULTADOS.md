# Resultados — detecção de anomalias de valor

Modelo selecionado **antes de abrir o teste**: **Desvio historico**. Critério: maior Average Precision (AP) na validação.

## Protocolo

- Treino: 2024 (17.692 transações). Validação: janeiro–junho/2025 (11.077). Teste: julho–dezembro/2025 (11.023).
- Fit dos modelos e do pré-processamento apenas no treino, sem rótulos e sem remover anomalias conhecidas pelo gabarito.
- Contexto atualizado sequencialmente com dias anteriores, inclusive durante validação/teste; pesos dos modelos ficam congelados.
- Limiar de cada modelo escolhido pelo F1 na validação. Nenhum limiar ou modelo foi escolhido pelas métricas de teste.
- AP resume o ranking; precisão/recall/F1 usam o limiar fixado. Scores não são probabilidades de fraude.

## Comparação

| Modelo | AP validação | AP teste | Precisão teste | Recall teste | F1 teste |
|---|---:|---:|---:|---:|---:|
| Desvio historico | 0.9812 | 0.9864 | 99.14% | 95.98% | 0.9753 |
| Isolation Forest | 0.7956 | 0.8296 | 89.18% | 76.56% | 0.8239 |
| Autoencoder | 0.2944 | 0.3515 | 40.84% | 36.48% | 0.3853 |

## Modelo selecionado no teste

Foram identificadas **692 de 721 anomalias**, com **6 falsos positivos** e **29 falsos negativos**.
Taxa de alerta: **6.33%**. Prevalência de anomalias: **6.54%**.
Nos 5% maiores scores, precisão **100.00%** e recall **76.56%**.

Intervalo aproximado de 95% para AP: **[0.9781; 0.9928]**, bootstrap de 200 amostras por semana.
O intervalo é condicional aos pesos e ao limiar fixos; não mede a incerteza de todo o processo de seleção nem garante validade fora da simulação.

## Análise de erros

- Inflacao: 463/485 detectadas (recall 95.46%).
- Reducao: 229/236 detectadas (recall 97.03%).
- Parceiros/tipos sem histórico no dia: 27 transações, incluindo 2 anomalias. O baseline exige pelo menos cinco transações passadas e pode não alertar nesses casos.
- Os casos individuais estão em `casos_erro.csv`; mecanismos de injeção só aparecem na análise posterior, nunca nas features.

## Interpretação e limites

O baseline contextual superou a rede neural neste experimento. A injeção altera o valor por multiplicadores expressivos, enquanto o comportamento normal de cada parceiro é relativamente estável; comparar ao histórico é especialmente eficaz nesse cenário.
O autoencoder reconstrói a entrada e foi treinado com uma base contaminada. Um erro de reconstrução pequeno não garante ausência de anomalia. Esta comparação usa uma arquitetura fixa, sem busca extensiva de hiperparâmetros; não demonstra inferioridade geral de redes neurais.
Valores líquidos e descontos foram excluídos porque a injeção preserva o desconto absoluto original e pode deixar um atalho artificial. Status, liquidações, saldos, rating agregado, IDs de transação/parceiro, chaves técnicas e gabarito também não entram na matriz. Códigos de área e categoria entram como contexto categórico.
As anomalias são artificiais; não representam fraude comprovada ou risco de inadimplência. Uma única série sintética, uma seed e um corte temporal não demonstram generalização para empresas reais. A EDA descritiva inspeciona toda a base; o protocolo de teste não é um estudo confirmatório pré-registrado.

## Referências metodológicas

- [Isolation Forest — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.ensemble.IsolationForest.html)
- [MLPRegressor — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.neural_network.MLPRegressor.html)
- [Average Precision — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.metrics.average_precision_score.html)
