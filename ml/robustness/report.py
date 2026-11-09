"""Relato e visualizacao dos desafios, sem alterar a selecao original."""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import StrMethodFormatter

from ml.config import REPORTS
from ml.plotting import BLUE, LIGHT, NAVY, PALETTE, canvas, save_figure
from .ablations import GROUP_LABELS

SCENARIO_LABELS = {
    "original": "Gerador original", "sutis": "Anomalias sutis", "extremos_legitimos": "Extremos legítimos",
    "mudanca_regime": "Mudança de regime", "combinado": "Combinado",
}


def load_results(destination):
    metrics = pd.read_csv(destination / "metricas_desafios.csv")
    ablations = pd.read_csv(destination / "ablacoes.csv")
    audit = json.loads((destination / "auditoria.json").read_text(encoding="utf-8"))
    selected = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))["selecionado"]
    return metrics, ablations, audit, selected


def write_report(destination):
    metrics, ablations, audit, selected = load_results(destination)
    grouped = metrics.groupby(["cenario", "modelo"])[["average_precision", "precision", "recall", "f1", "taxa_alerta", "fpr_normais", "fpr_extremos_legitimos", "fpr_normais_regime"]].agg(["mean", "min", "max"])
    grouped.to_csv(destination / "resumo_cenarios.csv")
    chosen = metrics[metrics.modelo == selected]
    summary = chosen.groupby("cenario").agg(ap=("average_precision", "mean"), precision=("precision", "mean"), recall=("recall", "mean"), f1=("f1", "mean"), minimo=("f1", "min"), maximo=("f1", "max"), fpr=("fpr_normais", "mean"))
    negative = audit["controle_negativo"]
    lines = ["# Auditoria e robustez — anomalias de valor", "",
             "**Conclusão:** os números altos se repetem dentro do gerador original, mas o desempenho não se sustenta nos desafios mais difíceis. O experimento inicial mede uma tarefa sintética favorável; não demonstra robustez operacional.", "",
             "## Auditoria do experimento original", "",
             "Foram verificados histórico por filtros independentes em 150 transações, atributos proibidos, mutação de dados futuros, períodos/IDs, cópias exatas de negócios, estatísticas do scaler e reprodução de scores/métricas."]
    for check in audit["verificacoes"]:
        lines.append(f"- {'Passou' if check['aprovado'] else 'Divergência'}: {check['verificacao']}.")
    lines += ["", "Essas verificações não encontraram vazamento direto ou erro aritmético. Não são uma prova de ausência de todo vazamento possível, nem de realismo dos dados.",
              f"No controle negativo, embaralhar os rótulos 100 vezes levou a AP média **{negative['ap_permutada_media']:.4f}** (mínimo {negative['ap_permutada_min']:.4f}, máximo {negative['ap_permutada_max']:.4f}), contra **{negative['ap_observada']:.4f}** observada. Isso verifica associação com o rótulo; não valida a aplicação real.", "",
              "## Novos conjuntos independentes", "",
              "Três seeds novas (101, 202, 303), cinco cenários pareados por seed e os três modelos originais: 15 datasets e 45 avaliações. Cada fonte tem novos parceiros/observações. Pesos, pré-processamento e limiares ficaram congelados; nenhum resultado de desafio recalibrou o modelo.",
              "Os históricos das novas fontes usam seus dias anteriores. Apenas o segundo semestre/2025 entra nas métricas. A nova seed testa outra realização da mesma família geradora; não representa validação externa em dados empresariais.", "",
              f"### Modelo escolhido originalmente: {selected}", "",
              "Médias simples entre as três seeds; a faixa mostra mínimo e máximo, não intervalo de confiança.", "",
              "| Cenário | AP média | Precisão média | Recall médio | F1 médio | Faixa de F1 | Falsos alertas entre normais |",
              "|---|---:|---:|---:|---:|---|---:|"]
    for name, label in SCENARIO_LABELS.items():
        row = summary.loc[name]
        lines.append(f"| {label} | {row.ap:.4f} | {row.precision:.2%} | {row.recall:.2%} | {row.f1:.4f} | {row.minimo:.4f}–{row.maximo:.4f} | {row.fpr:.2%} |")
    lines += ["", "### Como interpretar os cenários", "",
              "- **Original:** mesmas regras amplas de injeção e pequena variação normal; a boa repetição mostra estabilidade dentro dessa família.",
              "- **Sutis:** multiplicadores 1,1–1,3 ou 0,7–0,9, mantendo o conjunto de transações adulteradas. As distribuições passam a se sobrepor mais.",
              "- **Extremos legítimos:** cerca de 5% dos registros normais recebem picos 1,5–3,5, com rótulo normal. Sem uma variável observável que explique o evento válido, alguns valores são indistinguíveis de adulterações. Este cenário explicita um limite de observabilidade do alvo, não apenas de algoritmo.",
              "- **Mudança de regime:** 30% dos parceiros passam a operar em nível 1,8 vezes maior a partir de julho/2025, sem mudança de rótulo por esse motivo. AP pode continuar razoável enquanto o F1 cai: ranking e calibração são problemas distintos.",
              "- **Combinado:** anomalias sutis, ruído multiplicativo legítimo extra (sigma log 0,25), picos legítimos e regime novo. É um stress test construído, não uma estimativa da frequência desses eventos em empresas reais.",
              "Os rótulos continuam significando adulteração artificial de valor, enquanto eventos legítimos podem ser estatisticamente atípicos. Para separar legitimidade de adulteração, pode ser necessário contexto operacional que esse dataset não contém.", "",
              "## Retirada de grupos de atributos", "",
              "As ablações são diagnósticos no dataset original já inspecionado. Cada variante ajustou o pré-processador/modelo só no treino e o limiar só na validação; as variantes não substituíram o selecionado original.",
              "A chave interna `so_historico` corresponde a **Desvios atuais + histórico**: inclui o desvio do valor da transação atual em relação ao passado. Não é um modelo que observa apenas o passado. O controle `sem_valor_atual` retira também esses desvios derivados.", "",
              "| Grupo | Modelo | AP validação | AP teste diagnóstico | F1 teste diagnóstico | Taxa de alerta |",
              "|---|---|---:|---:|---:|---:|"]
    for row in ablations.itertuples():
        label = GROUP_LABELS.get(row.grupo, row.grupo)
        lines.append(f"| {label} | {row.modelo} | {row.ap_validacao:.4f} | {row.average_precision:.4f} | {row.f1:.4f} | {row.taxa_alerta:.2%} |")
    lines += ["", "Retirar o histórico derruba os modelos aprendidos; retirar valor atual e todos os seus desvios deixa a AP próxima da prevalência. Recall de 100% com taxa de alerta de 100% é o comportamento trivial de alertar tudo, não um detector eficaz.",
              "Algumas variantes com menos contexto categórico melhoram os modelos aprendidos nesta análise exploratória. Isso sugere hipóteses para outra rodada; não é motivo para promover uma variante usando o teste já observado.", "",
              "## Resposta à suspeita inicial", "",
              "Os números originais não parecem decorrer de um vazamento direto detectável pelas verificações realizadas. O fator principal é a separação fácil criada pelo gerador: comportamento normal estável por parceiro e alterações artificiais expressivas.",
              f"O F1 médio do modelo escolhido passa de **{summary.loc['original', 'f1']:.4f}** no cenário original para **{summary.loc['sutis', 'f1']:.4f}** nas anomalias sutis e **{summary.loc['combinado', 'f1']:.4f}** no combinado. Portanto, a conclusão adequada é **bom desempenho na simulação simples, robustez insuficiente nos desafios avaliados**.", "",
              "## Próximos experimentos", "",
              "1. Fixar o significado operacional de anomalia: desvio estatístico, adulteração ou evento que exige revisão humana.",
              "2. Reservar uma fonte/seed/período ainda não inspecionado antes de testar melhorias sugeridas por esta análise.",
              "3. Comparar referências robustas e adaptação de regime usando só treino/validação; avaliar custos de falsos alertas e falta de histórico.",
              "4. Adicionar contexto observável de eventos legítimos, se disponível, para reduzir ambiguidades do rótulo.",
              "5. Tratar os desafios atuais como desenvolvimento/diagnóstico em futuras decisões: eles já foram observados.", "",
              "## Rastreabilidade", "",
              "O protocolo registra seeds, cenários, hashes dos métodos/dependências, versões, modelos/artefatos originais e configuração antes da execução. Reexecuções com método ou ambiente diferente são rejeitadas e exigem um novo `--run-id`. O registro é local, não um pré-registro externo.",
              "As saídas originais foram preservadas e conferidas por hash. Resultados completos, predições e datasets estão em pastas separadas da rodada. Os documentos de auditoria são evidência do que foi verificado; não certificam ausência de todo erro possível.", ""]
    path = destination / "ROBUSTEZ.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def make_figures(destination):
    metrics, ablations, audit, selected = load_results(destination)
    chosen = metrics[metrics.modelo == selected]
    summary = chosen.groupby("cenario").f1.agg(["mean", "min", "max"]).reindex(SCENARIO_LABELS)
    figures = []
    fig, ax = canvas("O resultado depende do cenário", f"{selected} • média e faixa mínimo–máximo de 3 seeds • sem recalibrar", size=(11, 5.5))
    y = np.arange(len(summary))
    ax.barh(y, summary["mean"], color=[NAVY, BLUE, BLUE, BLUE, LIGHT], height=.58)
    ax.errorbar(summary["mean"], y, xerr=np.vstack([summary["mean"] - summary["min"], summary["max"] - summary["mean"]]), fmt="none", ecolor=NAVY, capsize=4, lw=1.5)
    for i, value in enumerate(summary["mean"]):
        ax.text(min(value + .045, 1.03), i, f"{value:.3f}", va="center", color=NAVY, fontsize=11)
    ax.set_yticks(y, list(SCENARIO_LABELS.values()))
    ax.invert_yaxis()
    ax.set(xlim=(0, 1.12), xlabel="F1 no teste adicional")
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:.1f}"))
    fig.subplots_adjust(left=.25)
    figures.append(fig)
    matrix = metrics.groupby(["cenario", "modelo"]).f1.mean().unstack().reindex(SCENARIO_LABELS)
    matrix = matrix[["Desvio historico", "Isolation Forest", "Autoencoder"]]
    fig, ax = canvas("Comparação com escolhas congeladas", "F1 médio entre três seeds • nenhum modelo é promovido por estes resultados", size=(10, 6.5))
    ax.imshow(matrix, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(3), ["Desvio histórico", "Isolation Forest", "Autoencoder"])
    ax.set_yticks(range(5), list(SCENARIO_LABELS.values()))
    for i in range(5):
        for j in range(3):
            value = matrix.iloc[i, j]
            ax.text(j, i, f"{value:.3f}", ha="center", va="center", color="white" if value > .5 else NAVY, fontsize=13)
    fig.subplots_adjust(left=.27)
    figures.append(fig)
    data = ablations[ablations.modelo != "Regra"]
    groups = list(GROUP_LABELS)
    fig, ax = canvas("De onde vem o poder de discriminação", "Ablações no dataset original já observado • Average Precision, não seleção de produção", size=(11, 6))
    for offset, model, color in [(-.12, "Isolation Forest", NAVY), (.12, "Autoencoder", BLUE)]:
        series = data[data.modelo == model].set_index("grupo").average_precision.reindex(groups)
        ax.scatter(series, np.arange(len(groups)) + offset, s=75, color=color, label=model)
    ax.set_yticks(range(len(groups)), [GROUP_LABELS[g] for g in groups])
    ax.invert_yaxis()
    ax.set(xlim=(0, 1), xlabel="Average Precision no teste diagnóstico")
    ax.legend(frameon=False, loc="lower right")
    fig.subplots_adjust(left=.33)
    figures.append(fig)
    negative = audit["controle_negativo"]
    fig, ax = canvas("Controle negativo com rótulos embaralhados", "100 permutações • testa associação, sem demonstrar realismo ou causalidade", size=(11, 4.5))
    values = [negative["ap_observada"], negative["ap_permutada_media"]]
    ax.barh([0, 1], values, color=[NAVY, LIGHT], height=.5)
    ax.set_yticks([0, 1], ["Rótulo original", "Rótulo permutado"])
    for i, value in enumerate(values):
        ax.text(value + .02, i, f"{value:.3f}", va="center", color=NAVY)
    ax.invert_yaxis()
    ax.set(xlim=(0, 1.12), xlabel="Average Precision (média no controle permutado)")
    fig.subplots_adjust(left=.25)
    figures.append(fig)
    for i, fig in enumerate(figures, 1):
        save_figure(fig, f"robustez_{i:02d}", f"robustness/{destination.name}")
    return figures
