"""Figuras do problema, atributos, periodos e resultados do experimento."""

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve, roc_curve

from .config import REPORTS
from .data import load_labels
from .plotting import BLUE, LIGHT, NAVY, PALETTE, barh, canvas, histogram, line, save_figure


def problem_figures(transactions):
    # Diagnostico de rotulos restrito ao treino; teste so aparece em resultados.
    train = transactions[transactions.data < "2025-01-01"].copy()
    labels = load_labels(train.id_transacao_natural)
    train["anomalia"] = labels.flag_anomalia.to_numpy()
    train["fator_aplicado"] = labels.fator_aplicado.to_numpy()
    counts = train.anomalia.value_counts().rename(index={False: "Normal", True: "Anomalia injetada"})
    figures = [barh(counts, "O alvo do experimento", "Somente treino (2024) • anomalia de valor injetada pelo gerador", "Transações", top=2)]
    fig, ax = canvas("Valores altos não bastam para definir anomalia", "Sobreposição de distribuições no treino • densidade em log(1 + valor bruto)")
    bins = np.linspace(np.log1p(train.valor_bruto.min()), np.log1p(train.valor_bruto.max()), 42)
    for label, color, text in [(False, LIGHT, "Normal"), (True, BLUE, "Anomalia injetada")]:
        ax.hist(np.log1p(train.loc[train.anomalia == label, "valor_bruto"]), bins=bins, density=True, alpha=0.65, color=color, label=text, edgecolor="white", linewidth=0.3)
    ax.set_xlabel("log(1 + valor bruto em R$)")
    ax.set_ylabel("Densidade")
    ax.legend(frameon=False)
    figures.append(fig)
    figures.append(histogram(train.loc[train.anomalia, "fator_aplicado"], "Como as anomalias são produzidas", "Multiplicadores aplicados no treino • variável do gabarito, proibida como feature", "Multiplicador do valor original"))
    audit = pd.DataFrame({"classe": np.where(train.anomalia, "Anomalia", "Normal"), "desconto_pct": 100 * (train.valor_bruto - train.valor_liquido) / train.valor_bruto})
    return figures, audit.groupby("classe").desconto_pct.agg(["min", "median", "max"]).reset_index()


def feature_figures(features):
    train = features[features.data < "2025-01-01"]
    figures = [histogram(train.z_historico, "Desvio em relação ao histórico do parceiro", "Treino • referência calculada somente com dias anteriores", "Desvio absoluto padronizado (log do valor)")]
    selected = ["log_valor", "desvio_log_historico", "z_historico", "log_qtd_historico", "desvio_log_90d", "z_90d", "log_qtd_90d"]
    names = ["Log valor", "Desvio histórico", "Z histórico", "Log frequência", "Desvio 90 dias", "Z 90 dias", "Log freq. 90 dias"]
    correlation = train[selected].corr()
    fig, ax = canvas("Relações entre os atributos numéricos", "Correlação de Pearson no treino • redundância não implica vazamento", size=(10, 7))
    image = ax.imshow(correlation.to_numpy(), cmap="Blues", vmin=-1, vmax=1)
    ax.set_xticks(range(len(names)), names, rotation=35, ha="right", fontsize=8)
    ax.set_yticks(range(len(names)), names, fontsize=9)
    for i in range(len(names)):
        for j in range(len(names)):
            value = correlation.iloc[i, j]
            ax.text(j, i, f"{value:.2f}", ha="center", va="center", color="white" if value > .55 else NAVY, fontsize=8)
    fig.colorbar(image, ax=ax, shrink=.7, label="Correlação")
    fig.subplots_adjust(left=.24, bottom=.23)
    figures.append(fig)
    return figures


def split_figure(summary):
    fig, ax = canvas("Separação temporal do experimento", "Treino → validação → teste • nenhum dia aparece em mais de um conjunto", size=(11, 4.5))
    for i, row in enumerate(summary.itertuples()):
        start, end = pd.Timestamp(row.inicio), pd.Timestamp(row.fim)
        ax.barh(i, (end - start).days + 1, left=start, color=PALETTE[i], height=.5)
        ax.text(start + (end - start) / 2, i, f"{row.registros:,} transações", color="white" if i < 2 else NAVY, ha="center", va="center", fontsize=10)
    ax.set_yticks(range(3), ["Treino · 2024", "Validação · 1º sem./2025", "Teste · 2º sem./2025"])
    ax.invert_yaxis()
    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m/%Y"))
    fig.subplots_adjust(left=.25)
    return fig


def validation_figures():
    metrics = pd.read_csv(REPORTS / "metricas_validacao.csv")
    figures = [barh(metrics.set_index("modelo").average_precision, "Comparação antes do teste final", "Average Precision na validação • maior é melhor", "Average Precision", top=3)]
    # Para metricas entre 0 e 1, nao usar o arredondamento de contagens.
    ax = figures[0].axes[0]
    for text, value in zip(ax.texts, metrics.set_index("modelo").average_precision.sort_values()):
        text.set_text(f"{value:.3f}")
    from matplotlib.ticker import StrMethodFormatter
    ax.xaxis.set_major_formatter(StrMethodFormatter("{x:.1f}"))
    ax.set_xlim(0, 1.12)
    loss = pd.read_csv(REPORTS / "autoencoder_loss.csv")
    figures.append(line(loss.set_index("epoca").loss_treino.rename("Treino"), "Aprendizado do autoencoder", "Erro de reconstrução no treino • não é métrica de detecção no teste", "Erro quadrático médio"))
    # O formatador de contagens nao e adequado a perdas fracionarias.
    figures[-1].axes[0].yaxis.set_major_formatter(StrMethodFormatter("{x:.3f}"))
    figures[-1].axes[0].set_xlabel("Época")
    return figures


def result_figures():
    results = pd.read_csv(REPORTS / "predicoes_teste.csv", parse_dates=["data"])
    metrics = pd.read_csv(REPORTS / "metricas_teste.csv")
    selection = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))
    winner = selection["selecionado"]
    figures = []
    fig, ax = canvas("Precisão e sensibilidade no teste final", "Curvas calculadas após congelar modelos e limiares • AP na legenda")
    for i, name in enumerate(metrics.modelo):
        subset = results[results.modelo == name]
        precision, recall, _ = precision_recall_curve(subset.y, subset.score)
        ap = float(metrics.set_index("modelo").loc[name, "average_precision"])
        ax.plot(recall, precision, color=PALETTE[i], lw=2.2, label=f"{name} · AP {ap:.3f}")
    prevalence = results[results.modelo == winner].y.mean()
    ax.axhline(prevalence, color=LIGHT, linestyle="--", lw=1.3, label=f"Referência aleatória · {prevalence:.1%}")
    ax.set(xlabel="Sensibilidade (recall)", ylabel="Precisão", xlim=(0, 1.01), ylim=(0, 1.03))
    ax.legend(frameon=False, loc="lower left", fontsize=9)
    figures.append(fig)
    row = metrics.set_index("modelo").loc[winner]
    fig, ax = canvas("Acertos e erros do modelo selecionado", f"{winner} • limiar definido na validação, sem ajuste no teste", size=(8, 6))
    matrix = np.array([[row.tn, row.fp], [row.fn, row.tp]], dtype=int)
    ax.imshow(matrix, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(j, i, f"{matrix[i, j]:,}".replace(",", "."), ha="center", va="center", fontsize=23, color="white" if matrix[i, j] > matrix.max() / 2 else NAVY)
    ax.set_xticks([0, 1], ["Normal", "Alerta"])
    ax.set_yticks([0, 1], ["Normal", "Anomalia"])
    ax.set_xlabel("Predição")
    ax.set_ylabel("Gabarito")
    figures.append(fig)
    chosen = results[results.modelo == winner].copy()
    monthly = chosen.assign(mes=chosen.data.dt.to_period("M").dt.to_timestamp()).groupby("mes").agg(Anomalias=("y", "sum"), Alertas=("predicao", "sum"))
    figures.append(line(monthly, "Estabilidade dos alertas no período de teste", "Contagens mensais • sem recalibrar o limiar", "Transações"))
    subtypes = chosen[chosen.y == 1].groupby("tipo_anomalia").agg(total=("y", "size"), detectados=("predicao", "sum"))
    recalls = subtypes.detectados / subtypes.total
    fig, ax = canvas("Detecção por mecanismo de anomalia", "Taxa de detecção no teste • o mecanismo só é usado nesta análise de erros")
    ax.bar(["Inflação de valor", "Redução de valor"], recalls.reindex(["inflacao", "reducao"]), color=[NAVY, BLUE], width=.55)
    for i, name in enumerate(["inflacao", "reducao"]):
        ax.text(i, recalls[name] + .025, f"{recalls[name]:.1%}\n({subtypes.loc[name, 'detectados']}/{subtypes.loc[name, 'total']})", ha="center", fontsize=11)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Sensibilidade (recall)")
    figures.append(fig)
    for i, fig in enumerate(figures, 1):
        save_figure(fig, f"resultado_{i:02d}", "experimento")
    return figures
