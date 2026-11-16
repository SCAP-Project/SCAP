"""Relatório, figuras e notebook da extensão documental; sem treinamento."""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import precision_recall_curve

from .config import ROOT
from .context_run import DEST
from .notebooks import md, code, write
from .plotting import BLUE, NAVY, LIGHT, canvas, save_figure


def load_results():
    return (
        json.loads((DEST / "resumo.json").read_text(encoding="utf-8")),
        pd.read_csv(DEST / "validacao.csv"),
        pd.read_csv(DEST / "teste_agregado.csv"),
        pd.read_csv(DEST / "segmentos.csv"),
    )


def make_figures():
    summary, validation, test, segments = load_results()
    winner = summary["selecionado"]
    data = test[test.cenario == "nominal"].set_index("modelo")
    names = ["Original congelado", "HGB sem contexto", "Regra documental", winner]
    names = list(dict.fromkeys(names))
    figures = []
    fig, ax = canvas(
        "O que mudou ao acrescentar contexto documental?",
        "Comparação nas mesmas transações de cinco clientes sintéticos reservados",
        size=(10, 5.3),
    )
    positions = np.arange(len(names))
    for shift, metric, label, color in [
        (-0.2, "precision", "Precisão", NAVY),
        (0, "recall", "Recall", BLUE),
        (0.2, "f1", "F1", LIGHT),
    ]:
        vals = data.loc[names, metric]
        ax.bar(positions + shift, vals, width=0.19, color=color, label=label)
    ax.set_xticks(
        positions,
        [
            n.replace(" congelado", "\ncongelado")
            .replace(" sem contexto", "\nsem contexto")
            .replace(" com contexto", "\ncom contexto")
            .replace(" documental", "\ndocumental")
            for n in names
        ],
    )
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False, ncol=3)
    figures.append(fig)
    scenarios = (
        test[test.modelo == winner]
        .set_index("cenario")
        .loc[["nominal", "documentos_degradados", "sem_documentos"]]
    )
    fig, ax = canvas(
        "O ganho depende da fonte documental",
        "Mesmos valores, rótulos e limiar; somente os documentos são degradados",
        size=(10, 5),
    )
    for shift, metric, label, color in [
        (-0.18, "precision", "Precisão", NAVY),
        (0.18, "recall", "Recall", LIGHT),
    ]:
        ax.bar(
            np.arange(3) + shift,
            scenarios[metric],
            width=0.32,
            label=label,
            color=color,
        )
    ax.set_xticks(
        range(3), ["Documento nominal", "Documentos degradados", "Sem documentos"]
    )
    ax.set_ylim(0, 1.05)
    ax.legend(frameon=False)
    figures.append(fig)
    predictions = pd.read_csv(DEST / "predicoes_teste.csv")
    fig, ax = canvas(
        "Separação dos casos no teste reservado",
        "AP e curvas de precisão/recall; sem recalibrar no teste",
        size=(10, 5),
    )
    for name, color in [("HGB sem contexto", LIGHT), (winner, NAVY)]:
        subset = predictions[
            (predictions.cenario == "nominal") & (predictions.modelo == name)
        ]
        p, r, _ = precision_recall_curve(subset.y, subset.score)
        ax.plot(
            r,
            p,
            label=f'{name} (AP {data.loc[name,"average_precision"]:.3f})',
            color=color,
            lw=2,
        )
    ax.set(xlim=(0, 1.02), ylim=(0, 1.02), xlabel="Recall", ylabel="Precisão")
    ax.legend(frameon=False)
    figures.append(fig)
    for i, fig in enumerate(figures, 1):
        save_figure(fig, f"contexto_{i:02d}", "contexto/rodada_03")
    return figures


def section_cells():
    return [
        md(
            "## Extensão com contexto documental anterior à transação\n\n"
            "Nova hipótese sintética de informação, não uma correção retroativa dos dados antigos. "
            "Os modelos e a comparação sem contexto usam os mesmos lotes. "
            "Quantidade e preço documental são emitidos antes do lançamento e antes da adulteração, "
            "com ruído, ausência e erros independentes do rótulo."
        ),
        code(
            """from ml.context_run import DEST as CONTEXT_RESULTS
from ml.context_report import make_figures as context_figures
from ml.data import sha256 as context_sha256
from ml.config import ROOT as CONTEXT_ROOT
context_protocol=json.loads((CONTEXT_RESULTS / "protocolo.json").read_text(encoding="utf-8"))
for filename,expected in context_protocol["metodos_sha256"].items():
    assert context_sha256(CONTEXT_ROOT/filename)==expected, filename
display(Markdown((CONTEXT_RESULTS / "RESULTADOS_CONTEXTO.md").read_text(encoding="utf-8")))
display(pd.read_csv(CONTEXT_RESULTS / "validacao.csv").round(4))
display(pd.read_csv(CONTEXT_RESULTS / "teste_agregado.csv").round(4))
display(pd.read_csv(CONTEXT_RESULTS / "segmentos.csv").round(4))
context_plots=context_figures()
if "show_figures" in globals():
    show_figures(context_plots,"6.6. Extensão documental")
else:
    for figure in context_plots:
        display(figure)
        plt.close(figure)
if "required" in globals():
    required.extend(CONTEXT_RESULTS/name for name in ["protocolo.json","selecao_congelada.json","resumo.json","validacao.csv","teste_agregado.csv","segmentos.csv","RESULTADOS_CONTEXTO.md"])
"""
        ),
    ]


def build_report():
    s, validation, test, segments = load_results()
    winner = s["selecionado"]
    n = s["nominal"]
    control = s["controle_sem_contexto"]
    selection = json.loads(
        (DEST / "selecao_congelada.json").read_text(encoding="utf-8")
    )
    degraded = test[
        (test.modelo == winner) & (test.cenario == "documentos_degradados")
    ].iloc[0]
    missing = test[(test.modelo == winner) & (test.cenario == "sem_documentos")].iloc[0]
    result = "atendeu" if s["criterio_sucesso_atendido"] else "não atendeu"
    report = f"""# Extensão supervisionada com contexto documental

## O que foi alterado

O histórico de valores tem capacidade limitada para distinguir uma operação legítima incomum de uma adulteração. Esta rodada acrescenta uma hipótese de informação: existe um pedido com quantidade e preço, emitido entre um e cinco dias antes da transação. É uma construção sintética proposta pelo projeto, não documentação empresarial observada.

O gerador foi refeito em duas etapas causais. Primeiro cria a operação comercial, picos legítimos, mudanças de quantidade, documento e faturamento normal. Depois um fluxo aleatório independente injeta adulteração somente no valor da transação. Os campos de documento não recebem `flag_anomalia`, fatores de injeção ou o valor do gabarito. A referência documental resulta da quantidade vezes o preço informados no pedido. Ela não é copiada do `valor_legitimo` dos experimentos anteriores.

Os documentos têm ruído logarítmico de 0,03 no preço, ausência esperada de 15% e probabilidade de erro adicional de 1,5%. O faturamento normal tem ruído logarítmico de 0,045. Essas intensidades são hipóteses experimentais, não estimativas de uma empresa. A taxa de adulteração permanece aproximadamente 4%, com metade de alterações sutis. Documentos ruidosos ou ausentes ocorrem independentemente da adulteração. Isso torna a nova tarefa uma detecção de inconsistência entre duas medições, além de raridade histórica.

## Treino, validação e teste

- Treino supervisionado: seis clientes, sementes120001–120006. Transações de março a junho/2026, com históricos desde janeiro. Foram {selection['n_treino']} exemplos, incluindo {selection['positivos_treino']} adulterações rotuladas pelo simulador. Nenhum rótulo é apresentado como investigação humana real.
- Validação: três outros clientes, sementes220001–220003, lote julho/2026 e históricos anteriores. Há {selection['n_validacao']} exemplos. Ajuste de limiar e escolha de candidato somente aqui.
- Teste reservado: cinco outros clientes, sementes320001–320005, lote setembro/2026 e históricos janeiro–agosto. Escolha e modelos foram congelados antes da geração e pontuação desses lotes.
- Candidatos fixos: original congelado, mediana anterior, regra de divergência documental, HGB sem documento, regressão logística com documento e HGB com documento.
- HGB usa 150 iterações, taxa0,07, até15 folhas, pelo menos40 exemplos por folha e regularizaçãoL2=1, sem early stopping ou busca após o teste. A referência sem contexto é treinada com os mesmos exemplos/rótulos e parâmetros.
- Seleção por F0,5 com recall mínimo de50% na validação. Critério experimental de sucesso no teste nominal: precisão>=60%, recall>=50% e AP/F1 superiores ao HGB sem contexto nas mesmas transações. Não se trata de meta de negócio validada.

## Resultado nominal pareado

O selecionado foi **{winner}**. Nos cinco clientes reservados há {int(n['n'])} transações e {int(n['anomalias'])} adulterações. A precisão foi **{n['precision']:.2%}**, o recall **{n['recall']:.2%}**, o F1 **{n['f1']:.4f}** e a AP **{n['average_precision']:.4f}**. Houve {int(n['alertas'])} alertas, {int(n['tp'])} verdadeiros positivos, {int(n['fp'])} falsos positivos e {int(n['fn'])} falsos negativos. O resultado **{result}** ao critério registrado.

O HGB sem contexto, treinado sobre os mesmos exemplos, teve precisão de {control['precision']:.2%}, recall de {control['recall']:.2%}, F1 de {control['f1']:.4f} e AP de {control['average_precision']:.4f}. Esta é a comparação apropriada para examinar a contribuição da informação adicional. Comparar diretamente estes números aos24,13% da rodada anterior misturaria populações e contratos diferentes. Todos os candidatos aparecem em `teste_agregado.csv`, sem promover outro modelo após olhar o teste.

## Dependência da qualidade documental

Com documentos degradados nos mesmos lotes, a precisão do selecionado foi {degraded.precision:.2%} e o recall {degraded.recall:.2%}. O desafio remove aleatoriamente 40% dos documentos, adiciona erros em 20% dos restantes e ruído logarítmico 0,08 ao preço. Sem documentos, a precisão foi {missing.precision:.2%} e o recall {missing.recall:.2%}, com apenas {int(missing.alertas)} alertas e {int(missing.tp)} verdadeiro positivo. A precisão de um conjunto tão pequeno de alertas não demonstra utilidade; {int(missing.fn)} adulterações ficaram sem detecção. O modelo e o limiar não foram recalibrados nos desafios. Os cenários são pareados e não correspondem a quinze clientes independentes.

O controle negativo com cinquenta permutações do gabarito produziu AP média de {s['controle_negativo_ap']:.4f}, comparada à prevalência de {n['prevalencia']:.2%}. Ele não substitui auditoria de disponibilidade da informação ou validação real.

## Limites e conclusão

O ganho depende da hipótese de um documento prévio parcialmente confiável. Esse campo não existe no CSV original, e não se afirma que o detector antigo passou a funcionar melhor sem nova informação. A nova abordagem é supervisionada, com rótulos artificiais; os experimentos antigos continuam não supervisionados. A capacidade de generalizar além do gerador e de processos com esse tipo de reconciliação não foi demonstrada. Um pedido incorreto pode produzir alerta falso e um documento ausente limita a detecção. Adulterações coordenadas do pedido e do lançamento não foram simuladas; padrões e faixas de multiplicadores do gerador podem favorecer o classificador.

O alvo completo de precisão>=60% e recall>=50% não foi atingido, pois o recall foi {n['recall']:.2%}. A distância para o piso de recall foi {max(0,.5-n['recall'])*100:.2f} ponto percentual. Não se alterou o limiar após observar essa diferença. O ganho de precisão, AP e F1 frente ao controle é apresentado separadamente da aprovação pelo critério completo.

Não foram acrescentados indicadores de autorização derivados do rótulo, alteradas as classes dos testes antigos ou filtrados os casos difíceis para elevar métricas. Uma adoção real exige confirmar disponibilidade, integridade e semântica do documento, obter rótulos confiáveis e realizar avaliação externa. O sistema sinaliza inconsistência, sem comprovar fraude.

## Inferência e reprodução

Usar as dependências de `ml/requirements.txt`, Python3.11/3.12. `python -m ml.context_run` reproduz o experimento. O contrato contém os sete campos originais e `id_documento`, `data_documento`, `quantidade_documento`, `preco_unitario_documento`. Os quatro campos documentais devem estar todos preenchidos ou todos ausentes. Documento preenchido deve ter data anterior ao lançamento.

`python -m ml.context_run --score-only --history HIST.csv --batch LOTE.csv --output SAIDA.csv` não abre gabarito nem recalibra o modelo. Os dados gerados, modelos e hashes ficam em `ml/artifacts/contexto/rodada_03` e `ml/reports/contexto/rodada_03`. O notebook08 e o consolidado apenas leem os resultados.
"""
    (DEST / "RESULTADOS_CONTEXTO.md").write_text(report, encoding="utf-8")
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
        ROOT / "ml/08_contexto_documental.ipynb",
        [
            md(
                "# Contexto documental e detecção supervisionada\n\nNova hipótese de dados com avaliação pareada e degradação de contexto."
            ),
            code(setup),
            *section_cells(),
        ],
    )
    for fig in make_figures():
        plt.close(fig)


if __name__ == "__main__":
    build_report()
