# SCAP — Sistema de Crédito e Anomalias Preditivas

Pipeline de dados financeiros sintéticos com ETL, análise exploratória e
detecção de anomalias de valor. O fluxo principal usa CSVs locais e Python;
não exige AWS, PostgreSQL ou credenciais.

## Estrutura

```text
etl/
  csv_pipeline/                ETL local: raw → trusted → refined
  data_generation/generators/  Geração dos dados sintéticos
  config/                     Configuração do fluxo PostgreSQL
  load_raw/                   Carga no PostgreSQL
  raw_to_trusted/              Transformações no PostgreSQL
  trusted_to_refined/          Modelo dimensional no PostgreSQL
ml/
  notebooks/eda/              Análise das dez tabelas de consumo
  notebooks/                 Atributos, divisão temporal, treino e resultados
  notebooks/robustness/       Auditoria e desafios de generalização
  datasets/                  Exemplos de histórico e lote de cliente
  robustness/                Experimentos de robustez
sql/                         DDL, permissões e migrações do fluxo PostgreSQL
tests/                       Testes unitários e de integração
```

`data/`, `ml/artifacts/` e os relatórios gerados são saídas locais. Não devem
ser usados como código-fonte nem incluídos nos commits.

## Instalação

Use Python 3.11 ou 3.12. No PowerShell, a partir da raiz do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r ml/requirements.txt
```

Para executar somente o ETL, instale `requirements-csv.txt`.
O arquivo `requirements.txt` atende ao fluxo PostgreSQL; suas dependências
não são necessárias para o processamento local.

## ETL

Na primeira execução, gere as fontes e processe as camadas:

```powershell
python -m etl.csv_pipeline --generate
```

Para reprocessar os CSVs existentes ou apenas validar:

```powershell
python -m etl.csv_pipeline
python -m etl.csv_pipeline --validate-only
```

Use `--data-dir caminho` para trabalhar em outra pasta. Preserve a camada
trusted entre execuções: ela mantém as chaves e o histórico das dimensões.
O manifesto `data/exports/etl_manifest.json` registra contagens e hashes.
Saídas anteriores são restauradas se uma substituição falhar.

O processamento produz seis dimensões — tempo, área, categoria contábil,
fornecedor/cliente, funcionário e moeda — e quatro fatos:

| Tabela em `data/refined/` | Registros do snapshot original |
|---|---:|
| `fact_transacoes_financeiras.csv` | 39.792 |
| `fact_pagamentos.csv` | 20.724 |
| `fact_recebimentos.csv` | 18.681 |
| `fact_saldos_diarios.csv` | 15.440 |

As parcelas fecham em centavos. Os saldos incluem dias sem movimento e são
separados por área e moeda; valores de moedas diferentes não são somados.

## Análise e modelos

Os dez notebooks em [ml/notebooks/eda](ml/notebooks/eda) apresentam cobertura,
nulos, distribuições e comportamento temporal de cada tabela. Os gráficos
usam tons de azul, fundo branco e nenhuma grade.

Para executar o experimento original e seus notebooks:

```powershell
python -m ml.run --stage all
```

Também é possível executar por etapa, nesta ordem:

```powershell
python -m ml.run --stage features
python -m ml.run --stage split
python -m ml.run --stage train
python -m ml.run --stage evaluate
python -m ml.run --stage notebooks
```

O experimento compara desvio histórico, Isolation Forest e um autoencoder
com `MLPRegressor`. O treino usa 2024; a validação, janeiro a junho de 2025;
o teste, julho a dezembro de 2025. O limiar e a escolha do modelo são
definidos na validação, antes da avaliação do teste.

Os atributos históricos usam somente dias anteriores ao lançamento.
Identificadores, liquidações, rating e campos do gabarito ficam fora da
matriz de entrada. O gabarito do experimento original serve à calibração e
à avaliação; não é usado para remover anomalias do treino.

### Robustez e simulação de cliente

Depois do experimento original, execute as extensões nesta ordem:

```powershell
python -m ml.robustness.run
python -m ml.client_demo
python -m ml.improvement
python -m ml.improvement_report
python -m ml.context_run
```

| Experimento | O que avalia | Notebook |
|---|---|---|
| Robustez | Vazamento, mudanças de regime, extremos legítimos e retirada de atributos | [Auditoria e desafios](ml/notebooks/robustness) |
| Cliente sintético | Aplicação do modelo congelado em um novo lote | [06_simulacao_cliente.ipynb](ml/06_simulacao_cliente.ipynb) |
| Novos candidatos | Histórico robusto e comparação em clientes reservados | [07_melhoria_modelo.ipynb](ml/07_melhoria_modelo.ipynb) |
| Contexto documental | Comparação supervisionada com e sem referência de pedido | [08_contexto_documental.ipynb](ml/08_contexto_documental.ipynb) |

As rodadas registram sementes, versões, critérios e hashes. Código alterado
não pode substituir silenciosamente uma rodada congelada. Para repetir
todos os experimentos com outra versão do código, use uma cópia de trabalho
sem artefatos anteriores. A inferência com `--score-only` reutiliza o modelo
existente e não exige novo treinamento.

### Entrada de cliente

Cada CSV contém uma linha por transação. Histórico e lote devem ter os
mesmos campos, IDs únicos e datas sem horário. Todo o histórico deve ser
anterior ao início do lote. Os exemplos de cliente usam valores em BRL.

| Campo | Conteúdo |
|---|---|
| `id_transacao_natural` | Identificador textual da transação |
| `data` | Data no formato `YYYY-MM-DD` |
| `id_parceiro_natural` | Identificador textual do parceiro |
| `valor_bruto` | Valor positivo, com ponto decimal |
| `tipo_transacao` | `RECEITA` ou `DESPESA` |
| `id_area_natural` | Código da área |
| `id_categoria_natural` | Código da categoria |

O modelo com contexto exige mais quatro colunas: `id_documento`,
`data_documento`, `quantidade_documento` e `preco_unitario_documento`.
Elas devem estar todas preenchidas ou todas ausentes na linha. A data do
pedido deve ser anterior à transação; quantidade e preço devem ser positivos.
O contrato simplifica a relação para um pedido único por transação, sem
rateios ou documentos compartilhados. O modelo compara o valor registrado
com `quantidade_documento × preco_unitario_documento`.

Após produzir os modelos, aplique um lote sem abrir o gabarito:

```powershell
python -m ml.client_demo --score-only --history HIST.csv --batch LOTE.csv --output PREVISOES.csv
python -m ml.context_run --score-only --history HIST_COM_PEDIDO.csv --batch LOTE_COM_PEDIDO.csv --output PREVISOES_CONTEXTO.csv
```

Há exemplos em `ml/datasets/cliente_dummy_01/` e
`ml/datasets/contexto_documental_03/`. Os rótulos de avaliação ficam separados
dos arquivos de entrada. A saída contém score, limiar, alerta e indicadores
de disponibilidade de contexto. Ausência de alerta não confirma normalidade.

### Resultados e limites

Na rodada documental, o treino contém 39.300 exemplos; a validação, 5.090;
o teste, 8.179 transações de cinco outros clientes sintéticos.

| HGB no mesmo teste | Precisão | Recall | AP |
|---|---:|---:|---:|
| Sem atributos documentais | 7,00% | 35,95% | 0,0800 |
| Com atributos documentais | 90,56% | 49,24% | 0,7409 |

O modelo com documentos gerou 163 alertas corretos e 17 falsos positivos,
deixando passar 168 alterações. O recall ficou abaixo da meta de 50%; o
critério completo de sucesso não foi atingido. Com documentos degradados,
a precisão caiu para 31,69%.

Os pedidos foram simulados e não existem nos CSVs originais. Essa rodada
estuda uma nova hipótese de dados e usa rótulos sintéticos no treinamento
supervisionado. Seus resultados não comprovam detecção de fraude,
inadimplência ou eficácia em operações reais. É necessária validação externa.

## Testes e formatação

```powershell
python -m pip install pytest==7.4.3 "black[jupyter]==23.12.0"
python -m pytest -q
python -m black --check etl ml tests
```

O padrão de formatação está em `pyproject.toml`. Ao usar VS Code ou Jupyter,
selecione o interpretador da `.venv`.

## Fluxo PostgreSQL

Os scripts de PostgreSQL preservam a implementação anterior. Para usá-los,
instale `requirements.txt` e configure as variáveis de `.env.example` em um
`.env` local. As definições ficam em `sql/ddl/`, numeradas de `00` a `06`.
Migrações em `sql/migrations/` atendem a versões antigas do esquema e não
fazem parte da criação de um banco novo. Senhas de exemplo devem ser
substituídas somente no ambiente local.
