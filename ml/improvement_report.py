"""Relatório e notebook da nova rodada; somente leitura dos experimentos."""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from .config import ROOT
from .improvement import DEST
from .notebooks import md, code, write
from .plotting import NAVY, LIGHT, canvas, save_figure


def make_figures():
    summary = json.loads((DEST / "resumo.json").read_text(encoding="utf-8"))
    data = pd.read_csv(DEST / "teste_agregado.csv").set_index("modelo")
    selected = summary["selecionado"]
    names = ["Original congelado", selected]
    figures = []
    fig, ax = canvas(
        "Precisão e detecção nos cinco clientes reservados",
        "Comparação no mesmo teste agregado; modelo escolhido antes de abrir o teste",
        size=(9, 4.8),
    )
    positions = np.arange(3)
    for shift, name, col in [(-0.18, names[0], LIGHT), (0.18, names[1], NAVY)]:
        vals = data.loc[name, ["precision", "recall", "f1"]].astype(float)
        ax.bar(positions + shift, vals, width=0.33, color=col, label=name)
        for x, v in zip(positions + shift, vals):
            ax.text(x, v + 0.015, f"{v:.1%}", ha="center", fontsize=10)
    ax.set_xticks(positions, ["Precisão", "Recall", "F1"])
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False)
    figures.append(fig)
    seeds = pd.read_csv(DEST / "teste_por_cliente.csv")
    fig, ax = canvas(
        "Variação da precisão entre clientes reservados",
        "Cinco realizações independentes do mesmo gerador; sem intervalos populacionais",
        size=(9, 4.8),
    )
    for name, col in zip(names, [LIGHT, NAVY]):
        subset = seeds[seeds.modelo == name]
        ax.plot(
            range(len(subset)),
            subset.precision,
            marker="o",
            lw=2,
            color=col,
            label=name,
        )
    ax.set_xticks(range(5), ["Cliente " + str(i) for i in range(1, 6)])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Precisão")
    ax.legend(frameon=False)
    figures.append(fig)
    predictions = pd.read_csv(DEST / "predicoes_teste.csv")
    fig, ax = canvas(
        "Qualidade do ranking no teste reservado",
        "Os pontos mostram os limiares congelados na validação",
        size=(9, 4.8),
    )
    for name, col in zip(names, [LIGHT, NAVY]):
        subset = predictions[predictions.modelo == name]
        precision, recall, _ = precision_recall_curve(subset.y, subset.score)
        ax.plot(
            recall,
            precision,
            color=col,
            label=f'{name} (AP {data.loc[name,"average_precision"]:.3f})',
            lw=2,
        )
        ax.scatter(
            data.loc[name, "recall"], data.loc[name, "precision"], color=col, s=55
        )
    ax.set(xlabel="Recall", ylabel="Precisão", xlim=(0, 1.02), ylim=(0, 1.02))
    ax.legend(frameon=False)
    figures.append(fig)
    for i, fig in enumerate(figures, 1):
        save_figure(fig, f"melhoria_{i:02d}", "melhoria/rodada_02")
    return figures


def section_cells():
    return [
        md(
            "## Nova rodada de melhoria com teste reservado\n\nEsta etapa foi planejada após observar os limites anteriores. "
            "Os experimentos antigos permanecem preservados. A seleção e a calibração usam novos clientes de desenvolvimento, "
            "e a avaliação final usa cinco novas sementes em maio de 2026. O lote antigo aparece apenas como diagnóstico posterior."
        ),
        code(
            """from ml.improvement import DEST as IMPROVEMENT_RESULTS
from ml.improvement_report import make_figures as improvement_figures
improvement_summary = json.loads((IMPROVEMENT_RESULTS / "resumo.json").read_text(encoding="utf-8"))
display(Markdown((IMPROVEMENT_RESULTS / "RESULTADOS_MELHORIA.md").read_text(encoding="utf-8")))
display(pd.read_csv(IMPROVEMENT_RESULTS / "validacao.csv").round(4))
display(pd.read_csv(IMPROVEMENT_RESULTS / "teste_agregado.csv").round(4))
display(pd.read_csv(IMPROVEMENT_RESULTS / "teste_por_cliente.csv").round(4))
improvement_plots=improvement_figures()
if "show_figures" in globals():
    show_figures(improvement_plots,"6.5. Nova rodada sem documentos")
else:
    for figure in improvement_plots:
        display(figure)
        plt.close(figure)
if "required" in globals():
    required.extend(IMPROVEMENT_RESULTS/name for name in ["protocolo.json","selecao_congelada.json","resumo.json","validacao.csv","teste_agregado.csv","RESULTADOS_MELHORIA.md"])
"""
        ),
    ]


def build_report():
    s = json.loads((DEST / "resumo.json").read_text(encoding="utf-8"))
    o = s["original"]
    n = s["novo"]
    known = pd.read_csv(DEST / "cliente_conhecido_diagnostico.csv").set_index("modelo")
    seeds = pd.read_csv(DEST / "teste_por_cliente.csv")
    selected = s["selecionado"]
    precision = seeds[seeds.modelo == selected].precision
    statement = "atendeu" if s["melhoria_criterio_predefinido"] else "não atendeu"
    report = f"""# Melhoria do detector com novo teste reservado

## Protocolo e separação

Os resultados antigos foram preservados. A rodada foi desenhada após inspecionar a simulação anterior. Não é uma confirmação cega de toda a pesquisa. A configuração foi registrada localmente antes da execução, em `protocolo.json`.

- Desenvolvimento: três clientes sintéticos, sementes 81001, 81002 e 81003. Históricos de janeiro a março de 2026 para ajuste não supervisionado; lotes de abril para calibração e escolha.
- Teste: cinco novos clientes, sementes 91001 a 91005, com histórico de janeiro a abril e lotes de maio de 2026. Nenhuma seleção usou estes resultados.
- Mesmas regras do gerador de cliente já conhecido, com novas realizações. A novidade dos registros não representa outra fonte empresarial nem garante generalização a outros geradores.
- Candidatos: original congelado, histórico recalibrado, medianas recentes em 20 e 60 dias e Isolation Forest contextual. O Isolation Forest usa dez atributos de desvios, dispersão, frequência e deslocamento recente, com padronização ajustada somente nos históricos de desenvolvimento, sem rótulos.
- Medianas e dispersões usam só dias anteriores. Escala: máximo entre 1,4826 vezes o desvio absoluto mediano e 0,10. Menos de cinco observações na janela leva à abstenção da regra, com score zero. Nenhuma ausência de alerta comprova normalidade.
- Seleção por maior F0,5 na validação, com recall mínimo de 35% e pelo menos dez alertas. Esse piso é experimental, não foi definido por uma área de negócio. Não há garantia de que se mantenha em cada novo cliente.
- Comparação final predefinida: precisão e F1 maiores que o original, sem perda de recall superior a dez pontos percentuais no teste agregado. Não houve alteração de candidatos após examinar o teste.

## Resultado no teste reservado

O selecionado foi **{selected}**. Nos cinco lotes, há {int(n['n'])} transações e {int(n['anomalias'])} adulterações. A precisão passou de **{o['precision']:.2%} para {n['precision']:.2%}**; o recall, de **{o['recall']:.2%} para {n['recall']:.2%}**; e o F1, de **{o['f1']:.4f} para {n['f1']:.4f}**. A AP foi {o['average_precision']:.4f} no original e {n['average_precision']:.4f} no selecionado.

O original emitiu {int(o['alertas'])} alertas, com {int(o['tp'])} verdadeiros positivos e {int(o['fp'])} falsos positivos. A nova configuração emitiu {int(n['alertas'])} alertas, com {int(n['tp'])} verdadeiros positivos, {int(n['fp'])} falsos positivos e {int(n['fn'])} falsos negativos. O resultado **{statement}** ao critério de melhoria registrado. Todos os candidatos, inclusive os não selecionados, estão em `teste_agregado.csv`.

A precisão por cliente do selecionado variou de {precision.min():.2%} a {precision.max():.2%}. A métrica agregada junta as transações dos cinco lotes, não é a média simples das precisões. A comparação é pareada dentro de cada lote. Não se atribui significância estatística ou intervalo populacional a apenas cinco realizações sintéticas.

## Lote antigo como diagnóstico

No lote já conhecido, a nova configuração obteve precisão de {known.loc[selected,'precision']:.2%}, recall de {known.loc[selected,'recall']:.2%} e F1 de {known.loc[selected,'f1']:.4f}. Esse resultado é retrospectivo e fica separado do teste reservado. Os 14,85% anteriores continuam documentados como resultado da configuração original.

## Interpretação e limites

Precisão maior precisa ser interpretada junto ao recall e ao volume de alertas. O detector continua recebendo somente valores e contexto de transação. Um pico legítimo e uma adulteração podem ser observacionalmente semelhantes. Nenhum dado de autorização ou explicação operacional foi inventado para facilitar a tarefa. Não foi demonstrada prontidão para produção ou prevenção de fraude.

Uma nova calibração em dados que se aproximam do ambiente de aplicação pode mudar bastante o ponto de operação. A comparação separa o ganho da decisão de limiar do ganho da representação: a linha de histórico recalibrado preserva exatamente o score antigo. O vencedor é escolhido na validação e não substituído por outro candidato que eventualmente pareça melhor no teste.

## Reprodução

Python 3.11/3.12 e as versões declaradas em `ml/requirements.txt`. Executar `python -m ml.improvement` a partir da raiz. O protocolo inclui versões, sementes e hashes do código e dos {s['originais_preservados']} arquivos originais. Datasets, modelos e previsões ficam em `ml/artifacts/melhoria/rodada_02` e `ml/reports/melhoria/rodada_02`. O notebook `ml/07_melhoria_modelo.ipynb` apenas lê os resultados, sem treinar ou reajustar.
"""
    (DEST / "RESULTADOS_MELHORIA.md").write_text(report, encoding="utf-8")
    path = ROOT / "ml/07_melhoria_modelo.ipynb"
    setup = """from pathlib import Path
import sys,json
import pandas as pd
import matplotlib.pyplot as plt
from IPython.display import display,Markdown
root=Path.cwd()
while not (root/'ml/config.py').exists():
    if root.parent==root:raise RuntimeError("Raiz do projeto não encontrada")
    root=root.parent
if str(root) not in sys.path:sys.path.insert(0,str(root))
"""
    write(
        path,
        [
            md(
                "# Melhoria da detecção de valores anômalos\n\nRodada independente de calibração e avaliação final, com resultados anteriores preservados."
            ),
            code(setup),
            *section_cells(),
        ],
    )
    for fig in make_figures():
        plt.close(fig)


if __name__ == "__main__":
    build_report()
