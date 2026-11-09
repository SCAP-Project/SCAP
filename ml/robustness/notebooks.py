"""Quatro notebooks de leitura dos experimentos adicionais, sem reabrir escolhas."""

from ml.config import ROOT
from ml.notebooks import SETUP, SHOW_FIGURES, code, md, write


def build_notebooks(destination):
    folder = ROOT / "ml/notebooks/robustness"
    relative = destination.relative_to(ROOT).as_posix()
    setup = SETUP + f'''\nimport json
DESTINATION = ROOT / "{relative}"
assert (DESTINATION / "protocolo_registrado.json").exists(), "Execute primeiro python -m ml.robustness.run"
'''
    paths = []
    path = folder / "01_auditoria_vazamento.ipynb"
    write(path, [
        md("# Auditoria do experimento original\n\nVerificar se o desempenho elevado decorre de vazamento direto, erro de cálculo ou uma simulação fácil. As verificações são evidências limitadas, não uma prova universal de ausência de vazamento. Execute primeiro `python -m ml.robustness.run` para produzir os artefatos desta rodada."),
        code(setup),
        md("## Testes independentes\n\n1. Recalcular médias e contagens por filtros diretos em 150 transações.\n2. Excluir atributos de gabarito, liquidação e snapshots.\n3. Multiplicar valores futuros por 20 e adulterar colunas proibidas: atributos passados devem permanecer iguais.\n4. Verificar períodos/IDs, cópias exatas, estatísticas do scaler e reprodução das métricas.\n\nEsses testes não avaliam realismo econômico. As mesmas identidades podem aparecer em épocas diferentes; o protocolo original avalia avanço no tempo, não uma população inteiramente nova."),
        code('''audit = json.loads((DESTINATION / "auditoria.json").read_text(encoding="utf-8"))
table = pd.DataFrame([{"Verificação": row["verificacao"], "Passou": row["aprovado"]} for row in audit["verificacoes"]])
display(style_table(table))
'''),
        md("## Controle negativo\n\nEmbaralhar os rótulos do teste quebra sua associação com os scores congelados. A AP resultante deve se aproximar da prevalência. Este controle não é uma prova causal ou de generalização; nenhum modelo é ajustado às permutações."),
        code('''negative = audit["controle_negativo"]
display(style_table(pd.DataFrame([negative]).drop(columns="nota").round(4)))
from ml.robustness.report import make_figures
figures = make_figures(DESTINATION)
display(figures[3])
for figure in figures:
    plt.close(figure)
'''),
        md("## Conclusão da auditoria\n\nAs verificações registradas não encontraram vazamento direto nem divergência na reprodução dos scores. A queda do controle permutado mostra que os scores estão associados ao rótulo original. Isso deixa aberta a hipótese principal: o gerador cria uma separação especialmente fácil entre valores normais e adulterados."),
    ])
    paths.append(path)
    path = folder / "02_cenarios_independentes.ipynb"
    write(path, [
        md("# Replicações independentes e cenários difíceis\n\nTrês novas seeds (101, 202 e 303), cada uma com cinco cenários pareados. Isso representa três realizações independentes com cinco variações cada, não quinze amostras independentes. Os três modelos, seus pré-processadores e seus limiares originais ficam congelados."),
        code(setup),
        md("## Regras definidas antes dos resultados\n\n- **Original:** regras do gerador existente, com nova seed.\n- **Sutis:** fatores 1,1–1,3 ou 0,7–0,9, mantendo as transações selecionadas como anomalia.\n- **Extremos legítimos:** cerca de 5% dos normais têm picos 1,5–3,5 e continuam com rótulo normal.\n- **Regime:** 30% dos parceiros passam a operar em nível 1,8 vezes maior a partir de julho/2025.\n- **Combinado:** sutis + ruído legítimo extra sigma log 0,25 + extremos + regime.\n\nAs sementes para ruído, eventos legítimos, regime e fatores são separadas. A avaliação usa apenas julho–dezembro/2025 e históricos de dias anteriores da nova fonte. Não há recalibração nos desafios. São simulações controladas, sem alegação de representar a frequência real desses eventos."),
        code('''metrics = pd.read_csv(DESTINATION / "metricas_desafios.csv")
selected = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))["selecionado"]
chosen = metrics[metrics.modelo == selected]
summary = chosen.groupby("cenario").agg(AP=("average_precision", "mean"), Precisão=("precision", "mean"), Recall=("recall", "mean"), F1=("f1", "mean"), F1_mínimo=("f1", "min"), F1_máximo=("f1", "max"), Falsos_alertas_normais=("fpr_normais", "mean")).reset_index()
display(style_table(summary.round(4)))
'''), code('''from ml.robustness.report import make_figures
figures = make_figures(DESTINATION)
for figure in figures[:2]:
    display(figure)
for figure in figures:
    plt.close(figure)
'''),
        md("## Limite de observabilidade\n\nUm pico legítimo e uma adulteração podem ter o mesmo valor e o mesmo histórico disponível. Sem uma variável que explique o evento legítimo, não existe garantia de distingui-los usando só esses atributos. Esse stress test questiona o alvo e as informações disponíveis, além do algoritmo.\n\nUma AP ainda alta acompanhada de queda no F1 pode indicar perda de calibração do limiar. Recalibrar exigiria outra validação; os desafios atuais não foram usados para esse ajuste."),
        code('''detail = metrics.groupby(["cenario", "modelo"])[["average_precision", "f1", "fpr_normais", "fpr_extremos_legitimos", "fpr_normais_regime"]].mean().reset_index()
display(style_table(detail.round(4)))
'''),
    ])
    paths.append(path)
    path = folder / "03_ablacao_atributos.ipynb"
    write(path, [
        md("# Ablação — de onde vem o desempenho?\n\nRetirar grupos de atributos para examinar dependências. Esta é uma análise diagnóstica no dataset original já observado. Não promove uma variante para produção e não fornece um novo teste independente de melhoria."), code(setup),
        md("## Grupos comparados\n\n- Completo.\n- Sem histórico: valor absoluto, calendário e categorias.\n- **Desvios atuais + histórico** (`so_historico`): inclui o valor atual relativo ao passado; não significa observar apenas o passado.\n- Sem categorias.\n- Sem calendário.\n- **Sem valor atual e derivados:** remove log do valor e todos os desvios/z que também carregam informação da transação atual.\n\nCada variante dos modelos aprendidos é ajustada só em 2024 e calibrada só no primeiro semestre/2025. Hiperparâmetros são os mesmos dos modelos originais; os pesos são reestimados em arquivos separados. As referências de regra comparam valor global, histórico completo e janela de 90 dias."),
        code('''from ml.robustness.ablations import FEATURE_GROUPS, GROUP_LABELS
groups = pd.DataFrame([{"Grupo": GROUP_LABELS[name], "Numéricos": ", ".join(numeric), "Categóricos": ", ".join(categorical)} for name, (numeric, categorical) in FEATURE_GROUPS.items()])
display(style_table(groups))
'''),
        code('''ablations = pd.read_csv(DESTINATION / "ablacoes.csv")
display(style_table(ablations[["grupo", "modelo", "ap_validacao", "average_precision", "precision", "recall", "f1", "taxa_alerta"]].round(4)))
'''), code('''from ml.robustness.report import make_figures
figures = make_figures(DESTINATION)
display(figures[2])
for figure in figures:
    plt.close(figure)
'''),
        md("## Interpretação\n\nO contraste com o histórico do parceiro concentra grande parte do sinal nesta simulação. A AP próxima da prevalência no controle sem valor atual/derivados é esperada. Recall de 100% com alertas em praticamente todas as linhas é uma solução trivial, não uma melhoria.\n\nVariantes mais simples podem melhorar modelos aprendidos no dataset observado. Essas descobertas são hipóteses para uma rodada futura com outro conjunto reservado, sem reutilizar o teste para confirmar a melhoria."),
    ])
    paths.append(path)
    path = folder / "04_conclusao_robustez.ipynb"
    write(path, [md("# Conclusão — os números eram altos demais?\n\nEste notebook reúne o diagnóstico, mantendo separados o resultado original e os desafios adicionais."), code(setup),
        code('''from ml.robustness.report import write_report
path = write_report(DESTINATION)
display(Markdown(path.read_text(encoding="utf-8")))
'''),
        md("## Preservação e rastreabilidade\n\nO protocolo registra métodos, dependências, versões, seeds e hashes dos artefatos originais. Um método diferente exige outro identificador de rodada. As tabelas originais e os modelos inicialmente avaliados não foram substituídos."),
        code('''from ml.robustness.run import original_files
protocol = json.loads((DESTINATION / "protocolo_registrado.json").read_text(encoding="utf-8"))
preserved = dict(originais_preservados=original_files() == protocol["originais_sha256"], arquivos_conferidos=len(protocol["originais_sha256"]))
display(style_table(pd.DataFrame([preserved])))
assert preserved["originais_preservados"]
''')])
    paths.append(path)
    return paths
