"""Gera notebooks separados e executa cada um com um kernel novo."""

from pathlib import Path
import sys

import nbformat as nbf

from .config import ROOT
from .eda import GRAINS, TABLE_ORDER, TITLES

DIRECTORY = ROOT / "ml/notebooks"
SETUP = '''from pathlib import Path
import sys
ROOT = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "ml").is_dir() and (p / "sql").is_dir())
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from IPython.display import display, Markdown
from ml.data import load_tables
from ml.plotting import configure_style, style_table, save_figure
from ml.config import REPORTS, ARTIFACTS
get_ipython().run_line_magic("matplotlib", "inline")
configure_style()
pd.set_option("display.max_columns", 40)
'''
SHOW_FIGURES = '''for figure in figures:
    display(figure)
    plt.close(figure)
'''


def md(text):
    return nbf.v4.new_markdown_cell(text)


def code(text):
    return nbf.v4.new_code_cell(text)


def write(path, cells):
    notebook = nbf.v4.new_notebook(cells=cells)
    notebook.metadata.update(kernelspec=dict(display_name="Python (SCAP ML)", language="python", name="python3"), language_info=dict(name="python", version="3.12"))
    path.parent.mkdir(parents=True, exist_ok=True)
    nbf.write(notebook, path)


def build_notebooks():
    paths = []
    for index, name in enumerate(TABLE_ORDER, 1):
        path = DIRECTORY / "eda" / f"{index:02d}_{name}.ipynb"
        cells = [md(f"# {TITLES[name]}\n\n**Tabela:** `{name}` · **Grão:** {GRAINS[name]}.\n\nAnálise descritiva do snapshot CSV. Figuras em azul, sem grade de fundo; PNG e SVG são exportados em `ml/reports/figures/eda/`. As relações usam as chaves vinculadas às versões do cadastro."),
                 code(SETUP), code(f'''from ml.eda import overview, profile, analyze_table
tables = load_tables()
df = tables["{name}"]
overview("{name}", df)
'''), md("## Estrutura e qualidade\n\nConfira nulos e cardinalidade. `vigencia_fim` vazia é esperada em versões atuais; prazo médio vazio é esperado em parceiros sem histórico. Colunas constantes não devem ser interpretadas como evidência preditiva."),
                 code("display(style_table(profile(df)))"), md("## Distribuições e comportamento\n\nAs unidades e regras de agregação aparecem em cada figura. Valores financeiros descrevem o dataset sintético em BRL."),
                 code(f'''figures, notes = analyze_table("{name}", tables)
{SHOW_FIGURES}'''), md("## Conclusões da tabela"), code('display(Markdown("\\n\\n".join("- " + note for note in notes)))'),
                 md("## Relação com o modelo\n\nA detecção usa somente atributos conhecidos no lançamento e históricos de dias anteriores. Esta análise é descritiva; tabelas de liquidação, saldos, RH e ratings completos não entram automaticamente no treinamento.")]
        write(path, cells)
        paths.append(path)

    objective = DIRECTORY / "01_objetivo_modelo.ipynb"
    write(objective, [md("# Objetivo — detectar valores anômalos\n\n**Pergunta:** no momento de um lançamento, o valor bruto é atípico em relação ao histórico disponível daquele parceiro e tipo de transação?\n\n**Unidade:** uma transação. **Alvo de avaliação:** `flag_anomalia`, que indica uma distorção artificial do valor. Não é um rótulo de fraude, cancelamento ou inadimplência. O diagnóstico de rótulos abaixo usa apenas 2024."), code(SETUP),
        md("## O que o gerador simula\n\nO gerador seleciona aproximadamente 6% das transações de cada parceiro (arredondamento para cima). Entre elas, cerca de 70% recebem multiplicadores entre 1,5 e 3,5 e cerca de 30% entre 0,2 e 0,6. Valores normais variam e parceiros podem ter tendências crescentes ou decrescentes. A taxa não é imposta exatamente por mês."),
        code('''from ml.diagnostics import problem_figures
transactions = load_tables()["fact_transacoes_financeiras"]
figures, shortcut_audit = problem_figures(transactions)
for i, figure in enumerate(figures, 1):
    save_figure(figure, f"problema_{i:02d}", "experimento")
    display(figure)
    plt.close(figure)
'''), md("## Possíveis atalhos e limitações\n\nNa injeção, o valor bruto muda, mas o desconto absoluto original é preservado. A porcentagem de desconto pode denunciar a regra sintética. Por isso, `valor_liquido`, desconto e razão líquido/bruto ficam fora da matriz principal. A tabela abaixo diagnostica esse risco, usando só o treino."), code("display(style_table(shortcut_audit.round(3)))"),
        md("## Protocolo escolhido\n\n- Treino não supervisionado em 2024, sem consultar o gabarito para remover anomalias.\n- Validação no primeiro semestre de 2025: escolher modelo por AP e limiar por F1.\n- Teste final no segundo semestre de 2025: avaliação sem novos ajustes.\n- Atualizar apenas o contexto com transações de dias anteriores; pesos dos modelos e pré-processamento ficam congelados.\n- Comparar baseline histórico, Isolation Forest e autoencoder.\n- Excluir status, liquidações, saldos, rating/prazo agregado, IDs técnicos e todas as colunas do gabarito.\n\n**Critério de sucesso:** superar referências simples e examinar precisão, recall, F1, AP, volume de alertas e erros. Sem custos operacionais definidos, o limiar F1 é uma escolha experimental, não um limiar de produção."),
        md("## Fontes\n\n[Isolation Forest](https://scikit-learn.org/1.3/modules/generated/sklearn.ensemble.IsolationForest.html) · [Rede MLP](https://scikit-learn.org/1.3/modules/generated/sklearn.neural_network.MLPRegressor.html) · [Average Precision](https://scikit-learn.org/1.3/modules/generated/sklearn.metrics.average_precision_score.html).")])
    paths.append(objective)

    feature_path = DIRECTORY / "02_criacao_atributos.ipynb"
    write(feature_path, [md("# Criação dos atributos\n\nAs transformações são implementadas em `ml/features.py`. Nenhuma coluna do gabarito é lida por essa etapa. O histórico é agregado por parceiro e tipo de transação, excluindo o dia inteiro do lançamento atual: a fonte não tem horários que permitam ordenar eventos dentro do dia."), code(SETUP),
        code('''from ml.experiment import prepare_features
from ml.features import MODEL_FEATURES
features = prepare_features()
display(style_table(pd.read_csv(REPORTS / "dicionario_atributos.csv")))
'''),
        md("## Contrato dos atributos\n\n- `log_valor`: log(1 + valor bruto), sem consultar a distribuição futura.\n- `desvio_log_*`: valor log atual menos média log histórica.\n- `z_*`: desvio absoluto dividido pelo desvio padrão histórico, com piso fixo 0,15.\n- Histórico completo e janela de 90 dias: contagens, médias e dispersão usam só dias anteriores.\n- Frequência e intervalo desde a última ocorrência; flag de ausência de histórico.\n- Calendário cíclico: seno e cosseno de mês/dia da semana.\n- Contexto categórico: tipo, área e categoria, codificados no treino.\n\n**Sem histórico:** os desvios são zero e há uma flag explícita; isso limita a detecção de parceiros novos. A janela de 90 dias não é um rótulo. IDs e estatísticas auxiliares permanecem para rastreabilidade, mas a matriz usa apenas a lista explícita `MODEL_FEATURES`.\n\nPré-processamento (padronização e one-hot) só será ajustado no treino. Variáveis redundantes são mantidas neste primeiro experimento fixo; a matriz de correlação documenta essa decisão."),
        code('''from ml.diagnostics import feature_figures
figures = feature_figures(features)
for i, figure in enumerate(figures, 1):
    save_figure(figure, f"atributos_{i:02d}", "experimento")
    display(figure)
    plt.close(figure)
'''), code('''display(style_table(features[["id_transacao_natural", "data", "valor_bruto", "qtd_historico", "media_log_historico", "z_historico", "sem_historico"]].head(8).round(3)))
print(f"Arquivo: ml/artifacts/features.csv • {len(features):,} linhas • {len(MODEL_FEATURES)} atributos de entrada")
''')])
    paths.append(feature_path)

    split_path = DIRECTORY / "03_divisao_temporal.ipynb"
    write(split_path, [md("# Treino, validação e teste por período\n\nOs limites foram fixados por calendário, sem procurar o corte que maximiza as métricas. Nenhum dia atravessa conjuntos. Este notebook não lê rótulos do teste."), code(SETUP),
        code('''from ml.experiment import prepare_split
features = prepare_split()
summary = pd.read_csv(REPORTS / "periodos.csv")
display(style_table(summary))
'''), code('''from ml.diagnostics import split_figure
figure = split_figure(summary)
save_figure(figure, "periodos", "experimento")
display(figure)
plt.close(figure)
'''),
        md("## Como o tempo é respeitado\n\n**Treino:** 01/01–31/12/2024. **Validação:** 01/01–30/06/2025. **Teste:** 01/07–31/12/2025.\n\nO histórico de cada exemplo contém apenas dias anteriores. No protocolo de scoring sequencial, uma transação observada na segunda-feira pode compor o contexto de terça-feira, mesmo no teste; seu rótulo não é utilizado. O modelo não é retreinado durante validação ou teste. Isso avalia monitoramento contínuo, não uma previsão de todo o semestre feita na véspera.\n\nOs mesmos parceiros podem aparecer nos três períodos. A avaliação mede avanço no tempo, não generalização a uma população inteiramente nova de parceiros."),
        code('''assert features.id_transacao_natural.is_unique
periods = {name: group for name, group in features.groupby("periodo")}
assert periods["treino"].data.max() < periods["validacao"].data.min()
assert periods["validacao"].data.max() < periods["teste"].data.min()
print("Verificado: chaves únicas, períodos disjuntos e ordem temporal preservada.")
''')])
    paths.append(split_path)

    training_path = DIRECTORY / "04_treino_comparacao.ipynb"
    write(training_path, [md("# Treinar e comparar modelos\n\nEste notebook ajusta modelos sem rótulos usando apenas o treino e compara seus scores na validação. O teste não participa da escolha. A execução grava modelos em `ml/artifacts/` e congela a seleção em `ml/reports/selecao_validacao.json`."), code(SETUP),
        md("## Três abordagens\n\n1. **Desvio histórico:** score = desvio padronizado absoluto no log do valor; exige cinco transações anteriores.\n2. **Isolation Forest:** 250 árvores, amostras de até 512 registros, seed 42. Scores invertidos para que valores maiores indiquem maior anomalia.\n3. **Autoencoder:** rede MLP com camadas 32 → 8 → 32, ReLU e saída linear, treinada para reconstruir a matriz; score = erro quadrático médio de reconstrução. Até 150 épocas, sem validação aleatória para early stopping.\n\nO autoencoder usa `MLPRegressor(X, X)` do scikit-learn e não exige GPU ou TensorFlow. Todos os modelos aprendidos recebem a mesma matriz (padronização numérica e one-hot ajustados só em 2024). O baseline usa apenas a referência histórica. A base de treino inclui anomalias desconhecidas; não há filtragem pelo gabarito."),
        code('''from ml.experiment import train
validation_metrics = train()
columns = ["modelo", "average_precision", "roc_auc", "precision", "recall", "f1", "taxa_alerta", "limiar"]
display(style_table(validation_metrics[columns].round(4)))
'''), code('''from ml.diagnostics import validation_figures
figures = validation_figures()
for i, figure in enumerate(figures, 1):
    save_figure(figure, f"validacao_{i:02d}", "experimento")
    display(figure)
    plt.close(figure)
'''),
        md("## Escolha congelada\n\nA maior Average Precision escolhe o modelo; empates usam F1 e nome. Cada limiar maximiza F1 na validação (empate: maior limiar). Isso é **calibração com rótulos de validação**, embora o ajuste dos pesos seja não supervisionado. AP é a média ponderada das precisões ao longo do recall, não a integral trapezoidal da curva. Não há obrigação de uma rede neural superar uma regra contextual."),
        code('''import json
selection = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))
display(Markdown(f"**Modelo selecionado antes do teste: {selection['selecionado']}.**"))
for name, info in selection["modelos"].items():
    if info["avisos"]:
        print(name, info["avisos"])
''')])
    paths.append(training_path)

    result_path = DIRECTORY / "05_resultados.ipynb"
    write(result_path, [md("# Resultados no teste final\n\nModelos, transformações e limiares já foram congelados na validação. As comparações abaixo não alteram a escolha. Este notebook também produz `ml/reports/RESULTADOS.md` com interpretação, erros e limitações."), code(SETUP),
        code('''from ml.experiment import evaluate_test
from ml.results import write_summary
test_metrics = evaluate_test()
summary_text = write_summary()
display(style_table(test_metrics[["modelo", "selecionado_na_validacao", "average_precision", "precision", "recall", "f1", "alertas", "fp", "fn"]].round(4)))
'''), code('''from ml.diagnostics import result_figures
figures = result_figures()
''' + SHOW_FIGURES),
        md("## Incerteza das métricas\n\nBootstrap de 200 reamostragens de semanas inteiras do teste, mantendo os pesos e o limiar fixos. Os intervalos não incluem incerteza de seleção nem demonstram desempenho em dados reais."),
        code('''display(style_table(pd.read_csv(REPORTS / "intervalos_bootstrap_semanal.csv").round(4)))
'''), md("## Casos de erro\n\nOs exemplos abaixo servem para compreender limitações. Ajustar o modelo com base nesses casos exigiria um novo teste independente."),
        code('''errors = pd.read_csv(REPORTS / "casos_erro.csv")
display(style_table(errors[["id_transacao_natural", "data", "valor_bruto", "qtd_historico", "score", "tipo_anomalia", "erro"]].head(12).round(3)))
'''), md("## Interpretação completa"), code("display(Markdown(summary_text))")])
    paths.append(result_path)
    return paths


def execute_notebooks(paths):
    if sys.platform == "win32":
        import asyncio
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    from nbclient import NotebookClient
    from nbconvert import HTMLExporter
    output = ROOT / "ml/reports/html"
    output.mkdir(parents=True, exist_ok=True)
    for path in paths:
        print(f"Executando {path.relative_to(ROOT)}...", flush=True)
        notebook = nbf.read(path, as_version=4)
        client = NotebookClient(notebook, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(ROOT)}})
        manager = client.create_kernel_manager()
        manager.kernel_spec.argv = [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"]
        client.execute()
        nbf.write(notebook, path)
        html, _ = HTMLExporter().from_notebook_node(notebook)
        (output / f"{path.stem}.html").write_text(html, encoding="utf-8")
