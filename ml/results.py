"""Relatorio legivel e analise de erros sem reselecionar modelos no teste."""

import json

import pandas as pd

from .config import REPORTS


def write_summary():
    selection = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))
    validation = pd.read_csv(REPORTS / "metricas_validacao.csv")
    test = pd.read_csv(REPORTS / "metricas_teste.csv")
    predictions = pd.read_csv(REPORTS / "predicoes_teste.csv")
    name = selection["selecionado"]
    winner = test.set_index("modelo").loc[name]
    chosen = predictions[predictions.modelo == name]
    subtype = chosen[chosen.y == 1].groupby("tipo_anomalia").agg(transacoes=("y", "size"), detectadas=("predicao", "sum"))
    subtype["recall"] = subtype.detectadas / subtype.transacoes
    subtype.to_csv(REPORTS / "erros_por_mecanismo.csv")
    errors = chosen[chosen.y != chosen.predicao.astype(int)].copy()
    errors["erro"] = errors.y.map({0: "falso_positivo", 1: "falso_negativo"})
    errors.sort_values(["erro", "score"], ascending=[True, False]).to_csv(REPORTS / "casos_erro.csv", index=False)
    intervals = pd.read_csv(REPORTS / "intervalos_bootstrap_semanal.csv", index_col=0)
    lines = [
        "# Resultados — detecção de anomalias de valor", "",
        f"Modelo selecionado **antes de abrir o teste**: **{name}**. Critério: maior Average Precision (AP) na validação.", "",
        "## Protocolo", "",
        "- Treino: 2024 (17.692 transações). Validação: janeiro–junho/2025 (11.077). Teste: julho–dezembro/2025 (11.023).",
        "- Fit dos modelos e do pré-processamento apenas no treino, sem rótulos e sem remover anomalias conhecidas pelo gabarito.",
        "- Contexto atualizado sequencialmente com dias anteriores, inclusive durante validação/teste; pesos dos modelos ficam congelados.",
        "- Limiar de cada modelo escolhido pelo F1 na validação. Nenhum limiar ou modelo foi escolhido pelas métricas de teste.",
        "- AP resume o ranking; precisão/recall/F1 usam o limiar fixado. Scores não são probabilidades de fraude.", "",
        "## Comparação", "",
        "| Modelo | AP validação | AP teste | Precisão teste | Recall teste | F1 teste |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in test.itertuples():
        apval = validation.set_index("modelo").loc[row.modelo, "average_precision"]
        lines.append(f"| {row.modelo} | {apval:.4f} | {row.average_precision:.4f} | {row.precision:.2%} | {row.recall:.2%} | {row.f1:.4f} |")
    lines += ["", "## Modelo selecionado no teste", "",
              f"Foram identificadas **{int(winner.tp)} de {int(winner.anomalias)} anomalias**, com **{int(winner.fp)} falsos positivos** e **{int(winner.fn)} falsos negativos**.",
              f"Taxa de alerta: **{winner.taxa_alerta:.2%}**. Prevalência de anomalias: **{winner.prevalencia:.2%}**.",
              f"Nos 5% maiores scores, precisão **{winner.precision_top_5pct:.2%}** e recall **{winner.recall_top_5pct:.2%}**.", "",
              f"Intervalo aproximado de 95% para AP: **[{intervals.loc['average_precision', 'limite_inferior_95']:.4f}; {intervals.loc['average_precision', 'limite_superior_95']:.4f}]**, bootstrap de 200 amostras por semana.",
              "O intervalo é condicional aos pesos e ao limiar fixos; não mede a incerteza de todo o processo de seleção nem garante validade fora da simulação.", "",
              "## Análise de erros", ""]
    for index, row in subtype.iterrows():
        lines.append(f"- {index.capitalize()}: {int(row.detectadas)}/{int(row.transacoes)} detectadas (recall {row.recall:.2%}).")
    cold = chosen[chosen.sem_historico == 1]
    lines += [f"- Parceiros/tipos sem histórico no dia: {len(cold)} transações, incluindo {int(cold.y.sum())} anomalias. O baseline exige pelo menos cinco transações passadas e pode não alertar nesses casos.",
              "- Os casos individuais estão em `casos_erro.csv`; mecanismos de injeção só aparecem na análise posterior, nunca nas features.", "",
              "## Interpretação e limites", "",
              "O baseline contextual superou a rede neural neste experimento. A injeção altera o valor por multiplicadores expressivos, enquanto o comportamento normal de cada parceiro é relativamente estável; comparar ao histórico é especialmente eficaz nesse cenário.",
              "O autoencoder reconstrói a entrada e foi treinado com uma base contaminada. Um erro de reconstrução pequeno não garante ausência de anomalia. Esta comparação usa uma arquitetura fixa, sem busca extensiva de hiperparâmetros; não demonstra inferioridade geral de redes neurais.",
              "Valores líquidos e descontos foram excluídos porque a injeção preserva o desconto absoluto original e pode deixar um atalho artificial. Status, liquidações, saldos, rating agregado, IDs de transação/parceiro, chaves técnicas e gabarito também não entram na matriz. Códigos de área e categoria entram como contexto categórico.",
              "As anomalias são artificiais; não representam fraude comprovada ou risco de inadimplência. Uma única série sintética, uma seed e um corte temporal não demonstram generalização para empresas reais. A EDA descritiva inspeciona toda a base; o protocolo de teste não é um estudo confirmatório pré-registrado.", "",
              "## Referências metodológicas", "",
              "- [Isolation Forest — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.ensemble.IsolationForest.html)",
              "- [MLPRegressor — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.neural_network.MLPRegressor.html)",
              "- [Average Precision — scikit-learn 1.3](https://scikit-learn.org/1.3/modules/generated/sklearn.metrics.average_precision_score.html)", ""]
    text = "\n".join(lines)
    (REPORTS / "RESULTADOS.md").write_text(text, encoding="utf-8")
    return text
