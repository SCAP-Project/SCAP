# ETL local em CSV

Atualizado em 09/11/2026. A conta AWS foi encerrada. O fluxo ativo e local;
os scripts PostgreSQL ficam preservados como implementacao anterior.

## Executar

Na raiz do repositorio, com Python 3.11 ou 3.12:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-csv.txt
python -m etl.csv_pipeline --generate
```

Nao e necessario `.env`, tunel SSH, banco de dados ou Jupyter. O gerador de
transacoes e executado a partir das celulas do notebook com um contexto novo.
Os demais geradores rodam depois, na ordem de suas dependencias.

Para transformar CSVs ja existentes, preservando historico e chaves:

```powershell
python -m etl.csv_pipeline
python -m etl.csv_pipeline --validate-only
python -m etl.csv_pipeline --data-dir caminho/para/data
```

`--generate` sobrescreve as fontes sinteticas correspondentes. Use-o apenas
quando quiser regenerar essas fontes. `--validate-only` nao substitui arquivos.
O codigo nao abre conexoes nem le configuracoes de banco.

## Fluxo e arquivos

1. Gerar transacoes de 2024/2025 e gabarito separado, usando seed 42.
2. Gerar areas, categorias, funcionarios, pagamentos e recebimentos.
3. Gerar parceiros e seus atributos derivados das liquidacoes corrigidas.
4. Ler e validar as sete entidades em `data/raw/<entidade>/*.csv`.
5. Transformar em oito tabelas em `data/trusted/<tabela>.csv`.
6. Construir seis dimensoes e quatro fatos em `data/refined/<tabela>.csv`.
7. Validar tudo em memoria, preparar arquivos temporarios, substituir as
   saidas e publicar `data/exports/etl_manifest.json` por ultimo.

O manifesto registra data de execucao UTC, dia de observacao, contagens e
SHA-256 dos arquivos de entrada e saida. `data/exports/generation.log`
guarda a saida dos geradores. Dados e logs nao sao versionados no Git.
Os atributos sinteticos usam seed 42; alguns geradores ainda usam UUIDs de
ingestao aleatorios. O hash do manifesto identifica cada snapshot concreto.

Antes da publicacao, qualquer erro de regra interrompe a execucao e preserva
as saidas anteriores. Uma falha de gravacao aciona restauracao dos arquivos
substituidos a partir de copias temporarias. Cada substituicao e atomica,
mas o conjunto nao e uma transacao de banco: queda do processo/disco pode
interromper a restauracao. A proxima execucao confere hashes e recusa um
estado divergente do manifesto. Nao execute cargas em paralelo nem leia
as tabelas durante sua substituicao.

## Tabelas para analise

Contagens da primeira execucao local em 09/11/2026:

| CSV em refined | Linhas | Grao |
|---|---:|---|
| dim_tempo | 1.461 | Data, calendario de 2023 a 2026 |
| dim_area | 20 | Versao de area |
| dim_categoria_contabil | 40 | Versao de categoria |
| dim_fornecedor_cliente | 250 | Versao de parceiro |
| dim_funcionario | 150 | Versao de funcionario |
| dim_moeda | 3 | Moeda BRL/USD/EUR |
| fact_transacoes_financeiras | 39.792 | Transacao |
| fact_pagamentos | 20.724 | Evento de pagamento |
| fact_recebimentos | 18.681 | Evento de recebimento, inclusive parcela |
| fact_saldos_diarios | 15.440 | Dia, area e moeda |

Os fatos incluem `data` no formato ISO, alem de `tempo_sk` no formato
numerico YYYYMMDD. As chaves de dimensao sao compartilhadas entre as camadas
CSV; nao sao as sequencias independentes da antiga implementacao PostgreSQL.

Pagamentos e recebimentos herdam `parceiro_sk` e `moeda_sk` da transacao.
Uma venda parcelada tem dois recebimentos cuja soma e igual ao valor liquido.
Operacoes ATRASADO mantem os ajustes financeiros do gerador; nao se exige que
seus valores sejam identicos ao liquido. ATRASADO neste dataset representa
liquidacao com atraso, nao uma divida que continua em aberto.

`fact_saldos_diarios` inclui os dias sem movimento entre a primeira e a ultima
liquidacao global, para cada combinacao de area/moeda observada:

```text
saldo_inicial = saldo_final do dia anterior (zero no primeiro dia)
saldo_final = saldo_inicial + entradas - saidas
```

Esses saldos representam o fluxo acumulado simulado a partir de zero;
nao sao o saldo bancario real de uma empresa. Nao some moedas diferentes.
O dataset sintetico atual tem transacoes somente em BRL.

## Historico e reexecucao

As dimensoes registram o dia em que a alteracao foi observada no ETL:

- Sem alteracao: preserva a versao e sua chave.
- Alteracao no mesmo dia: atualiza aquela versao, sem duplicar.
- Alteracao em outro dia: fecha a versao anterior e abre outra.
- Intervalo de validade: `[vigencia_inicio, vigencia_fim)`.
- Transacao ja existente: preserva as chaves das versoes originalmente
  vinculadas se a chave natural do cadastro nao mudou.
- Transacao nova: vincula a versao atual do cadastro.
- Remocao de fatos existentes: interrompe o ETL para impedir reutilizacao
  de chaves. Para outro dataset, use outra pasta em `--data-dir` e preserve
  uma copia do conjunto anterior.
- Data de observacao anterior a ultima execucao: rejeitada.

Essa politica nao reconstrui o cadastro historico de 2024 a partir de um
snapshot observado em 2026. Para preservar o historico, mantenha os CSVs
de trusted entre execucoes. Apaga-los inicia outro historico e pode gerar
outras chaves. Saldos sao recalculados integralmente em cada execucao.

## Analise e machine learning

```python
import pandas as pd

fato = pd.read_csv("data/refined/fact_transacoes_financeiras.csv",
                   dtype={"id_transacao_natural": str}, parse_dates=["data"])
parceiros = pd.read_csv("data/refined/dim_fornecedor_cliente.csv")
base = fato.merge(parceiros, on="parceiro_sk", validate="many_to_one")
```

Use `parceiro_sk` para o join, preservando a versao do cadastro; o join apenas
por chave natural pode multiplicar linhas quando houver historico.

O gabarito fica em `data/ground_truth/transacoes_gabarito.csv`, separado das
features. Junte `id_transacao_natural` a `id_transacao_raw` somente para
avaliacao. `rating_credito` e `prazo_medio` agregam todo o historico observado:
recalcule-os com dados passados para evitar vazamento temporal no treino.
`eh_feriado` permanece falso; `eh_dia_util` considera apenas segunda a sexta.

No Power BI, importe os CSVs como UTF-8, separador virgula e ponto decimal.
Defina colunas monetarias como decimal fixo e datas como data.

## Testes

```powershell
python -m pip install pytest==7.4.3
python -m pytest -q
```

Os testes usam diretorios temporarios e nao precisam de AWS ou `.env`.
