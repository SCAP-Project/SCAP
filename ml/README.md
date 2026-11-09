# Análise exploratória e detecção de anomalias

O objetivo é sinalizar **valores brutos atípicos no instante da transação**,
comparando cada lançamento ao histórico disponível do parceiro/tipo. A fonte
é o snapshot sintético local em `data/refined/`. Não há dependência de AWS.

## Abrir os notebooks

Todos estão executados e contêm as figuras e conclusões. A EDA tem um arquivo
por tabela; os gráficos usam tons de azul, fundo branco e nenhuma grade.

| Tabela | Notebook |
|---|---|
| Áreas | [01_dim_area.ipynb](notebooks/eda/01_dim_area.ipynb) |
| Categorias contábeis | [02_dim_categoria_contabil.ipynb](notebooks/eda/02_dim_categoria_contabil.ipynb) |
| Fornecedores/clientes | [03_dim_fornecedor_cliente.ipynb](notebooks/eda/03_dim_fornecedor_cliente.ipynb) |
| Funcionários | [04_dim_funcionario.ipynb](notebooks/eda/04_dim_funcionario.ipynb) |
| Moedas | [05_dim_moeda.ipynb](notebooks/eda/05_dim_moeda.ipynb) |
| Tempo | [06_dim_tempo.ipynb](notebooks/eda/06_dim_tempo.ipynb) |
| Transações | [07_fact_transacoes_financeiras.ipynb](notebooks/eda/07_fact_transacoes_financeiras.ipynb) |
| Pagamentos | [08_fact_pagamentos.ipynb](notebooks/eda/08_fact_pagamentos.ipynb) |
| Recebimentos | [09_fact_recebimentos.ipynb](notebooks/eda/09_fact_recebimentos.ipynb) |
| Saldos diários | [10_fact_saldos_diarios.ipynb](notebooks/eda/10_fact_saldos_diarios.ipynb) |

Cada EDA mostra grão, cobertura, nulos/cardinalidade, distribuições,
comportamento temporal quando aplicável e conclusões específicas. A EDA cobre
as dez tabelas de consumo de refined; raw/trusted são camadas internas do ETL.

As etapas do experimento também ficam separadas:

1. [Objetivo e problemas do dataset](notebooks/01_objetivo_modelo.ipynb).
2. [Criação dos atributos](notebooks/02_criacao_atributos.ipynb).
3. [Divisão temporal](notebooks/03_divisao_temporal.ipynb).
4. [Treino e comparação](notebooks/04_treino_comparacao.ipynb).
5. [Resultados e análise de erros](notebooks/05_resultados.ipynb).

Os notebooks de etapas devem ser executados nessa ordem. Cada um inicia um
kernel novo no executor; não depende de variáveis de uma sessão anterior.
Os artefatos produzidos pelas etapas anteriores são dependências explícitas.
Para abrir e executar no VS Code/Jupyter, selecione o Python da `.venv`.

## Reproduzir

Python 3.11 ou 3.12, na raiz do repositório:

```powershell
.\.venv\Scripts\python -m pip install -r ml/requirements.txt
# Somente se os dados locais ainda nao existirem:
.\.venv\Scripts\python -m etl.csv_pipeline --generate
# Pipeline completo, incluindo execucao dos quinze notebooks:
.\.venv\Scripts\python -m ml.run --stage all
```

Para executar por etapa:

```powershell
python -m ml.run --stage features
python -m ml.run --stage split
python -m ml.run --stage train
python -m ml.run --stage evaluate
python -m ml.run --stage notebooks
```

`notebooks` regenera e executa todos os notebooks, incluindo novo treino nas
etapas correspondentes. Edite `ml/notebooks.py` para manter alterações no
conteúdo ao regenerá-los. O modo `all` executa também as etapas em Python e
depois verifica sua reprodução nos notebooks, sem ajuste adaptativo no teste.
O notebook usado pelo gerador sintético já faz parte da origem; sua execução
ocorre no ETL. O experimento verifica os hashes de refined antes da leitura.

## Protocolo

| Conjunto | Período | Transações |
|---|---|---:|
| Treino | 2024 | 17.692 |
| Validação | Janeiro–junho de 2025 | 11.077 |
| Teste | Julho–dezembro de 2025 | 11.023 |

- Ajuste de pesos e pré-processamento apenas no treino, **sem rótulos**.
- O gabarito calibra o limiar por F1 e escolhe o modelo por AP na validação;
  esse uso dos rótulos é explícito. No teste, todas as escolhas ficam fixas.
- Contexto por parceiro/tipo usa só dias anteriores, sem ordem intradiária
  inventada. No scoring online, o contexto pode incorporar observações
  anteriores da validação/teste, mas nunca seus rótulos ou eventos futuros.
- Treino contaminado: não removemos anomalias com ajuda do gabarito.
- Modelos: baseline de desvio histórico, Isolation Forest e autoencoder
  `MLPRegressor(X, X)` com gargalo 32 → 8 → 32. Rede CPU, sem TensorFlow/GPU.
- Nenhuma busca adaptativa de hiperparâmetros após inspecionar o teste.
- Métricas: AP, AUROC, precisão, recall, F1, alertas e precisão/recall nos
  5% maiores scores. Bootstrap semanal de 200 amostras para o selecionado.

## Atributos e exclusões

Treze variáveis numéricas: valor em log, desvios e frequências históricas,
janela de 90 dias, tempo desde a última ocorrência, ausência de histórico e
calendário cíclico. Três contextos categóricos: tipo, área e categoria.
O `ColumnTransformer` usa apenas a lista `MODEL_FEATURES`; outras colunas do
CSV são rastreabilidade/diagnóstico. Não adicione colunas à matriz por seleção
genérica de tipos numéricos.

Ficam fora: IDs de transação/parceiro, chaves técnicas, status, liquidações,
saldos, rating e prazo médio de snapshot, todos os campos do gabarito e
valor líquido/desconto. A injeção preserva o desconto absoluto original,
então sua proporção pode denunciar a simulação e inflar o desempenho.

## Saídas

- `ml/artifacts/`: atributos, conjuntos por período, pré-processador e modelos.
- `ml/reports/`: métricas, scores, erros, intervalos, seleção e manifesto.
- `ml/reports/figures/`: figuras PNG e SVG para exportação.
- `ml/reports/html/`: cópias dos quinze notebooks em HTML.
- [RESULTADOS.md](reports/RESULTADOS.md): interpretação e limitações.

CSVs, JSONs, modelos, HTMLs e figuras regeneráveis ficam ignorados pelo Git;
os notebooks executados e o resumo Markdown ficam disponíveis no projeto.
O manifesto registra hashes de entradas, features e código, parâmetros,
versões e seed.

## Limites da conclusão

Uma avaliação adicional investiga esses limites em
[ROBUSTEZ.md](ROBUSTEZ.md), com auditoria, novas seeds, cenários difíceis,
ablação e quatro notebooks separados. Consulte-a junto dos números originais.

Anomalia injetada não significa fraude ou inadimplência. A entrada de novos
parceiros, a regra de dias úteis, o perfil monetário estável e os multiplicadores
amplos são características do gerador. A EDA descritiva usa o snapshot inteiro;
o teste não equivale a um estudo confirmatório pré-registrado. Para testar
melhorias motivadas pelos erros atuais, reserve outro período/dataset antes
de avaliar novamente.

## Testes

```powershell
python -m pip install pytest==7.4.3
python -m pytest -q
```

Os testes verificam exclusão do dia atual/futuro, janela de 90 dias, separação
por tipo, colunas proibidas, fronteiras temporais e limiares com empates.
