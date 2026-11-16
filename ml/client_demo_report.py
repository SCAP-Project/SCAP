"""Figuras e relato da simulação de upload; não altera modelos ou métricas."""

import json

import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from .client_demo import DATASET, DESTINATION
from .config import ROOT
from .notebooks import SETUP, code, md, write
from .plotting import BLUE, LIGHT, NAVY, canvas, save_figure


def load_results():
    manifest = json.loads((DATASET / "manifesto.json").read_text(encoding="utf-8"))
    metrics = json.loads((DESTINATION / "metricas.json").read_text(encoding="utf-8"))
    predictions = pd.read_csv(
        DESTINATION / "avaliacao_com_gabarito.csv", parse_dates=["data"]
    )
    segments = pd.read_csv(DESTINATION / "segmentos.csv")
    return manifest, metrics, predictions, segments


def make_figures():
    _, metrics, predictions, segments = load_results()
    figures = []
    fig, ax = canvas(
        "Acertos e erros no lote do cliente simulado",
        "Gabarito de adulteração artificial • inclui registros sem contexto suficiente",
        size=(8, 6),
    )
    matrix = np.array([[metrics["tn"], metrics["fp"]], [metrics["fn"], metrics["tp"]]])
    ax.imshow(matrix, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax.text(
                j,
                i,
                str(matrix[i, j]),
                ha="center",
                va="center",
                fontsize=24,
                color="white" if matrix[i, j] > matrix.max() / 2 else NAVY,
            )
    ax.set_xticks([0, 1], ["Sem alerta", "Alerta"])
    ax.set_yticks([0, 1], ["Normal", "Adulteração"])
    ax.set(xlabel="Saída do modelo", ylabel="Gabarito sintético")
    figures.append(fig)
    fig, ax = canvas(
        "Qualidade do ranking no envio simulado",
        "Modelo e limiar originais preservados • a curva não recalibra o detector",
    )
    precision, recall, _ = precision_recall_curve(
        predictions.flag_anomalia, predictions.score
    )
    ax.plot(
        recall,
        precision,
        color=BLUE,
        lw=2.4,
        label=f"Desvio histórico · AP {metrics['average_precision']:.3f}",
    )
    ax.axhline(
        metrics["prevalencia"],
        color=LIGHT,
        ls="--",
        label=f"Prevalência · {metrics['prevalencia']:.1%}",
    )
    ax.scatter(
        [metrics["recall"]],
        [metrics["precision"]],
        color=NAVY,
        s=65,
        zorder=3,
        label="Limiar da validação original",
    )
    ax.set(xlabel="Recall", ylabel="Precisão", xlim=(0, 1.02), ylim=(0, 1.04))
    ax.legend(frameon=False, loc="upper right", fontsize=9)
    figures.append(fig)
    by_segment = segments.set_index("segmento")
    fig, ax = canvas(
        "Quais adulterações foram detectadas?",
        "Recall por intensidade • inclui todos os parceiros; não é uma nova escolha de limiar",
    )
    names = ["Adulterações amplas", "Adulterações sutis"]
    values = by_segment.loc[names, "recall"]
    ax.barh(names, values, color=[NAVY, BLUE], height=0.5)
    for i, name in enumerate(names):
        row = by_segment.loc[name]
        ax.text(
            float(values.loc[name]) + 0.02,
            i,
            f"{values.loc[name]:.1%} ({int(row.tp)}/{int(row.anomalias)})",
            va="center",
        )
    ax.set(xlabel="Recall", xlim=(0, 1.25))
    ax.invert_yaxis()
    fig.subplots_adjust(left=0.27)
    figures.append(fig)
    fig, ax = canvas(
        "Eventos normais que geraram alertas",
        "Taxa de falso positivo dentro de cada segmento • grupos podem se sobrepor",
    )
    names = ["Lote completo", "Normais com pico legítimo", "Normais em regime novo"]
    for i, name in enumerate(names):
        row = by_segment.loc[name]
        ax.barh(i, row.fpr, color=[LIGHT, BLUE, NAVY][i], height=0.5)
        ax.text(
            row.fpr + 0.015,
            i,
            f"{row.fpr:.1%} ({int(row.fp)}/{int(row.n - row.anomalias)})",
            va="center",
        )
    ax.set_yticks(range(len(names)), names)
    ax.set(xlabel="Falsos alertas / registros normais do segmento", xlim=(0, 1.2))
    ax.invert_yaxis()
    fig.subplots_adjust(left=0.31)
    figures.append(fig)
    for i, fig in enumerate(figures, 1):
        save_figure(fig, f"cliente_{i:02d}", "cliente_dummy/rodada_01")
    return figures


def write_report():
    manifest, m, predictions, segments = load_results()
    s = segments.set_index("segmento")
    broad, subtle = s.loc["Adulterações amplas"], s.loc["Adulterações sutis"]
    cold, insufficient = s.loc["Parceiros novos"], s.loc["Contexto insuficiente (<5)"]
    peak, regime = s.loc["Normais com pico legítimo"], s.loc["Normais em regime novo"]
    protocol = json.loads((DESTINATION / "protocolo.json").read_text(encoding="utf-8"))
    text = f"""# Simulação de envio de dados pela área cliente

## Desenho e origem

Esta rodada simula uma área cliente que fornece histórico de janeiro a março de 2026 e envia um lote de abril de 2026. Os dados são inteiramente artificiais, em BRL, produzidos por um gerador novo, sem copiar transações ou valores do treino. Reutilizam-se apenas códigos válidos de tipo/área/categoria. A seed é {manifest['configuracao']['seed']}; as regras e os hashes foram registrados localmente antes de gerar dados ou medir resultados.

Há {manifest['configuracao']['parceiros_recorrentes']} parceiros recorrentes e {manifest['configuracao']['parceiros_novos']} parceiros com entrada prevista em abril. As datas representam o cenário simulado, não a data real de coleta de um cliente. O histórico tem **{manifest['linhas']['historico_cliente.csv']:,} transações**, e o lote tem **{m['n']:,} transações**, de **{predictions.data.min():%d/%m/%Y} a {predictions.data.max():%d/%m/%Y}**. Foram observados {predictions.id_parceiro_natural.nunique()} parceiros no lote.

O gerador usa escalas próprias por parceiro, dispersão log entre 0,12 e 0,28, frequência variável, pequena tendência e padrão semanal. A probabilidade de adulteração é 4% por registro, tanto no histórico quanto no lote; metade das adulterações, em expectativa, é sutil. A realização efetiva não precisa coincidir exatamente com essas proporções. Adulterações sutis usam fatores 1,1–1,3 ou 0,7–0,9; amplas usam 1,5–2,5 ou 0,35–0,65. Picos legítimos podem ocorrer em registros normais (probabilidade condicional de 1,5%). Quinze parceiros recorrentes passam a operar em nível 1,6 vez maior em abril, como mudança legítima.

## Separação entre entrada, inferência e avaliação

- `historico_cliente.csv`: contexto anterior ao lote, com sete campos observáveis.
- `lote_cliente.csv`: arquivo que representa o upload, com os mesmos sete campos e sem gabarito.
- `gabarito_avaliacao.csv`: adulterações, fatores e eventos legítimos; exclusivo da avaliação posterior, separado da inferência.
- `predicoes_upload.csv`: saída por transação, sem rótulos; score, limiar, alerta e indicação de contexto insuficiente.

O modelo **{protocol['modelo']}**, escolhido anteriormente na validação original, foi aplicado com limiar **{m['limiar']:.6f}**, sem treinamento, recalibração ou seleção de outro modelo. O histórico usa apenas dias anteriores; registros anteriores do próprio lote atualizam o contexto. Todos os registros do mesmo dia compartilham o mesmo passado. O CSV completo de abril não é usado como referência global para pontuar o início do mês.

O envio é simulado pelo processamento local de CSV. Não foi implementada uma interface web nem realizado um envio real por cliente. O modo `--score-only` permite repetir apenas a inferência sem abrir o gabarito. Com menos de cinco observações passadas, o baseline zera o score; a saída marca **CONTEXTO_INSUFICIENTE**, que não deve ser interpretado como comprovação de normalidade. Esses registros permanecem nas métricas globais.

## Resultados do lote

| Indicador | Resultado |
|---|---:|
| Transações avaliadas | {m['n']} |
| Adulterações no gabarito | {m['anomalias']} |
| Prevalência | {m['prevalencia']:.2%} |
| Alertas | {m['alertas']} ({m['taxa_alerta']:.2%}) |
| Verdadeiros positivos | {m['tp']} |
| Falsos positivos | {m['fp']} |
| Falsos negativos | {m['fn']} |
| Verdadeiros negativos | {m['tn']} |
| Precisão | {m['precision']:.2%} |
| Recall | {m['recall']:.2%} |
| F1 | {m['f1']:.4f} |
| Average Precision | {m['average_precision']:.4f} |

## Principais conclusões

1. **Intensidade da adulteração:** o detector identificou {int(broad.tp)} de {int(broad.anomalias)} adulterações amplas (recall {broad.recall:.1%}) e {int(subtle.tp)} de {int(subtle.anomalias)} sutis (recall {subtle.recall:.1%}). Essa diferença descreve esta realização; não é uma estimativa precisa para uma população empresarial.
2. **Custo de revisão:** {m['fp']} dos {m['alertas']} alertas foram falsos positivos em relação ao alvo de adulteração. A legitimidade não é inferida pelo score. O fluxo exige revisão humana, sem garantia de que cada alerta represente irregularidade.
3. **Eventos legítimos:** {int(peak.fp)} de {int(peak.n)} picos legítimos receberam alerta (FPR {peak.fpr:.1%}). Entre normais em regime novo, foram {int(regime.fp)} de {int(regime.n - regime.anomalias)} (FPR {regime.fpr:.1%}). Esses segmentos podem se sobrepor; não some seus totais. Um pico legítimo pode ser um alerta estatístico válido, embora seja falso positivo para o alvo de adulteração.
4. **Entrada de parceiros:** {int(cold.n)} registros pertencem a parceiros novos. Em todo o lote, {int(insufficient.n)} registros tiveram menos de cinco observações anteriores, incluindo {int(insufficient.anomalias)} adulterações. Essa limitação deve aparecer na avaliação de cobertura, além das métricas agregadas.
5. **Transferência do limiar:** o mesmo modelo e o mesmo limiar foram usados em uma nova construção sintética. O desempenho observado mede a aplicação congelada sob esse desenho; a análise não permite atribuir todas as falhas a uma causa única nem concluir que recalibração as resolveria.

## Interpretação dos resultados

“Foi conduzida uma simulação de recebimento de dados por uma área cliente, composta por um histórico anterior e um lote mensal de {m['n']} transações artificiais. O detector previamente selecionado foi aplicado sem novo ajuste de pesos ou limiar. Foram emitidos {m['alertas']} alertas, com {m['tp']} adulterações identificadas, {m['fp']} falsos positivos e {m['fn']} falsos negativos, resultando em precisão de {m['precision']:.2%}, recall de {m['recall']:.2%} e F1 de {m['f1']:.4f}. A análise por segmento evidenciou a sensibilidade à intensidade das adulterações, aos eventos legítimos atípicos e à disponibilidade de histórico. Os resultados caracterizam o comportamento do fluxo em uma simulação controlada e não constituem validação operacional com dados de clientes reais.”

## Limites e uso futuro

Esta rodada usa **uma seed, um cliente fictício e um mês**. Foi desenhada após conhecer os testes anteriores; é uma avaliação complementar de um fluxo de aplicação, não um estudo cego ou evidência independente da hipótese que motivou o desenho. Não fornece intervalo de generalização, validação externa ou prova de detecção de fraude. Dado sintético novo não equivale a dado real de cliente.

Esta rodada é uma simulação de aplicação em lote de cliente fictício. Os resultados complementam o experimento original e as três sementes de robustez. O lote passa a ser conhecido após a avaliação; melhorias motivadas por ele exigem outro teste reservado. Nenhum parâmetro foi alterado em resposta a esta rodada.

## Arquivos e reprodução

Dataset: `ml/datasets/cliente_dummy_01/`. Protocolo, saída da inferência, métricas e análise detalhada: `ml/reports/cliente_dummy/rodada_01/`. Figuras em PNG/SVG: `ml/reports/figures/cliente_dummy/rodada_01/`. Execute `python -m ml.client_demo` para reproduzir a rodada com verificações de integridade. O contrato de entrada e o comando de inferência estão no README principal.
"""
    path = DESTINATION / "RESULTADOS_CLIENTE.md"
    path.write_text(text, encoding="utf-8")
    return path


def build_notebook():
    path = ROOT / "ml/06_simulacao_cliente.ipynb"
    write(
        path,
        [
            md(
                """# Simulação de aplicação — envio de dados pela área cliente

Leitura da rodada já executada, sem treinamento ou geração de novos dados. O upload é um CSV local fictício, acompanhado de histórico anterior. O gabarito permanece separado da inferência. Esta rodada complementa o experimento original e os desafios de robustez.
"""
            ),
            code(
                SETUP
                + """
import json
from ml.client_demo import DATASET, DESTINATION
from ml.client_demo_report import make_figures, load_results
from ml.data import sha256
manifest, metrics, evaluated, segments = load_results()
manifest_path = DATASET / "manifesto.json"
for name, expected in manifest["arquivos_sha256"].items():
    assert sha256(DATASET / name) == expected, f"Entrada alterada: {name}"
integrity = json.loads((DESTINATION / "integridade.json").read_text(encoding="utf-8"))
assert sha256(manifest_path) == integrity["dataset_sha256"]
for name, expected in integrity["resultados_sha256"].items():
    assert sha256(DESTINATION / name) == expected, f"Resultado alterado: {name}"
"""
            ),
            md(
                "## 1. Arquivo enviado e saída operacional\n\nOs dados abaixo não possuem rótulos. `CONTEXTO_INSUFICIENTE` significa menos de cinco observações anteriores; ausência de alerta não atesta normalidade."
            ),
            code(
                """display(style_table(pd.read_csv(DATASET / "lote_cliente.csv").head(8)))
display(style_table(pd.read_csv(DESTINATION / "predicoes_upload.csv").head(8).round(3)))
"""
            ),
            md(
                "## 2. Resultados e cobertura por segmento\n\nRecall é mostrado quando há adulterações no segmento; FPR quando há normais. Células vazias não são zero. Segmentos podem se sobrepor."
            ),
            code(
                """display(style_table(pd.DataFrame([metrics]).round(4)))
display(style_table(segments.round(4)))
"""
            ),
            md(
                "## 3. Visualizações\n\nFonte: elaboração própria, dados sintéticos SCAP. Limiar fixado na validação original; nenhuma curva recalibra o modelo."
            ),
            code(
                """figures = make_figures()
for figure in figures:
    display(figure)
    plt.close(figure)
"""
            ),
            md(
                "## 4. Casos para inspeção\n\nO gabarito aparece somente nesta avaliação posterior. Os exemplos não servem para ajustar o limiar desta rodada."
            ),
            code(
                """cases = evaluated[evaluated.resultado.isin(["FP", "FN"])].sort_values("score", ascending=False)
display(style_table(cases[["id_transacao_natural", "data", "valor_bruto", "qtd_historico", "score", "situacao", "resultado", "mecanismo", "pico_legitimo", "regime_novo"]].head(12).round(3)))
"""
            ),
            md("## 5. Conclusões"),
            code(
                """display(Markdown((DESTINATION / "RESULTADOS_CLIENTE.md").read_text(encoding="utf-8")))
"""
            ),
        ],
    )
    return path
