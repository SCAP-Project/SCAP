# Guia da camada `refined`

Documento de referência para quem for consumir a camada `refined` para
análise de dados e machine learning (feature engineering, detecção de
anomalias, dashboards). Cobre o que já está pronto, o dicionário de dados
e os cuidados específicos deste dataset. Atualizado em 27/09/2026.

## 1. Onde as coisas estão

Arquitetura Medallion: `raw` (bruto, fiel à origem) → `trusted` (limpo,
padronizado, com histórico SCD Tipo 2) → `refined` (star schema, é a
camada de consumo analítico). Consumo de dados para modelagem e BI deve
ler apenas `refined` — `raw`/`trusted` são camadas internas do pipeline.

**Acesso ao banco:** RDS PostgreSQL privado, acesso via túnel SSH pelo EC2
Bastion Host (sessão PuTTY "RDS-SCAP", documentada em
`docs/aws/infraestrutura_aws.md`). Logins do grupo `cientista_dados` têm
leitura em `raw`/`trusted`/`refined` e leitura/escrita completa no schema
`ml` (destino de artefatos de experimento — features materializadas,
resultados de modelo, etc.).

## 2. O que já está pronto

Toda a camada `trusted` está populada (raw → trusted, as 7 entidades). Da
camada `refined`, está pronto:

| Tabela | Linhas | Observação |
|---|---:|---|
| `dim_tempo` | 1.461 | spine de datas 2023-01-01 a 2026-12-31 |
| `dim_moeda` | 3 | BRL/USD/EUR, mas **100% dos dados reais são BRL** |
| `dim_area` | 20 | departamentos |
| `dim_categoria_contabil` | 40 | categorias contábeis |
| `dim_fornecedor_cliente` | 250 | fornecedores/clientes, com rating de crédito |
| `dim_funcionario` | 150 | quadro de RH (não conecta a nenhum fato) |
| **`fact_transacoes_financeiras`** | **39.792** | **a tabela fato principal para modelagem** |

**Ainda não implementado:** `fact_pagamentos`, `fact_recebimentos`,
`fact_saldos_diarios`. Não bloqueiam o consumo de `fact_transacoes_financeiras`
— dependem apenas de mais tempo de ETL.

## 3. Dicionário de dados — schema `refined`

### 3.1 `fact_transacoes_financeiras` (a tabela central)

Grão: uma linha por transação financeira (`id_transacao_natural`, formato
`'TR-00144'`). Sem SCD Tipo 2 — é fato, não dimensão.

| Coluna | Tipo | Significado |
|---|---|---|
| `transacao_sk` | bigint (PK) | chave técnica, não usar como feature |
| `id_transacao_natural` | text | chave de negócio; é por ela que se junta com `ml.transacoes_gabarito` |
| `tempo_sk` | FK → `dim_tempo` | data da transação |
| `area_sk` | FK → `dim_area` | departamento que originou a transação |
| `parceiro_sk` | FK → `dim_fornecedor_cliente` | fornecedor ou cliente envolvido |
| `categoria_sk` | FK → `dim_categoria_contabil` | categoria contábil |
| `moeda_sk` | FK → `dim_moeda` | sempre BRL na prática |
| `valor_bruto` | decimal(18,2) | valor antes de qualquer desconto |
| `valor_liquido` | decimal(18,2) | valor efetivo (sempre ≤ `valor_bruto`) |
| `tipo_transacao` | text | `'RECEITA'` ou `'DESPESA'` |
| `forma_pagamento` | text | `PIX, BOLETO, TED, TRANSFERENCIA, CARTAO` |
| `status_pagamento` | text | `PAGO, ATRASADO, CANCELADO` — `ATRASADO` é o sinal mais relevante de risco de crédito neste dataset |
| `source_system` | text | metadado de origem, ignorar para modelagem |

Cobertura temporal real: transações até dez/2025, recebimentos (quando essa
fato existir) se estendem até fev/2026.

### 3.2 `dim_fornecedor_cliente` (já tem features de risco prontas)

Grão: um fornecedor/cliente, com histórico SCD2 (hoje só existe 1 versão de
cada, mas o schema já suporta versionar se o cadastro mudar).

| Coluna | Tipo | Significado |
|---|---|---|
| `parceiro_sk` | bigint (PK) | usar para juntar com o fato |
| `id_parceiro_natural` | text | chave de negócio |
| `nome_parceiro` | text | |
| `tipo_parceiro` | text | `CLIENTE`, `FORNECEDOR` ou `AMBOS` — derivado do fluxo real de transações (não do prefixo do id) |
| `documento`, `contato_email`, `contato_telefone`, `endereco`, `pais`, `estado`, `cidade`, `setor_atuacao` | text | cadastrais |
| `rating_credito` | text | `AAA, AA, A, BBB, BB, B, C, SEM_HISTORICO` — já derivado da taxa de inadimplência observada (ATRASADO+CANCELADO / total) |
| `prazo_medio` | int | média de dias entre transação e liquidação; `NULL` se `SEM_HISTORICO` |
| `is_current` | boolean | sempre TRUE hoje (sem histórico real ainda) |

Importante: `rating_credito`/`prazo_medio` são um snapshot agregado até o
momento da carga — não são point-in-time por transação. Uma feature do
tipo "rating do parceiro até a data desta transação" (evitando olhar para
o futuro) precisa ser recalculada a partir do fato, não usar esta coluna
direto como feature de treino sem considerar vazamento temporal.

### 3.3 `dim_tempo` (calendário pronto, sem custo)

Colunas: `tempo_sk`, `data`, `ano`, `semestre` (1/2), `trimestre` (1-4),
`mes`, `nome_mes`, `dia`, `dia_semana` (1=Segunda...7=Domingo),
`nome_dia_semana`, `semana_ano`, `eh_dia_util` (seg-sex), `eh_feriado`
(sempre FALSE — não há calendário de feriados móveis implementado, não
confiar nesta coluna).

### 3.4 `dim_area` / `dim_categoria_contabil`

Simples, sem pegadinha: `area_sk`/`categoria_sk` (PK), `id_*_natural`
(chave de negócio), atributos descritivos, colunas de SCD2 (hoje sem
histórico real). `dim_categoria_contabil.tipo_categoria` é `RECEITA` ou
`DESPESA` — deve bater com `fact.tipo_transacao` da mesma linha (mesma
lógica, redundante de propósito).

### 3.5 `dim_funcionario`

Existe para análises de RH (headcount, folha por área). Não se conecta a
nenhum fato — a origem não vincula funcionário a transação, então não há
como usar isso como feature de transação.

## 4. O gabarito de anomalias — `ml.transacoes_gabarito`

Este é o ground truth do experimento controlado (não faz parte do
Medallion de propósito — um ERP real não sabe dizer o que é anomalia).

| Coluna | Tipo | Significado |
|---|---|---|
| `id_transacao_raw` | text (PK) | junta com `fact.id_transacao_natural` |
| `data_transacao` | date | |
| `flag_anomalia` | boolean | o rótulo |
| `perfil_risco` | text | `normal, retencao, alto_valor, alto_valor_retencao` — mecanismo causal por trás do `status_pagamento`, útil só como referência/análise de erro |
| `flag_ajuste`, `flag_alto_valor` | boolean | detalhe da injeção |
| `fator_aplicado` | numeric | multiplicador aplicado no valor; `NULL` nas linhas normais |
| `valor_original` | numeric(18,6) | valor antes da injeção de anomalia |
| `valor_bruto` | numeric(18,6) | valor que foi para o raw (mais precisão que a versão em `refined`, que arredonda para 2 casas) |

**Regra de ouro: usar esta tabela SÓ na avaliação (precision/recall/F1/AUC-ROC),
nunca como feature de treino.** Nenhuma coluna dela deve entrar no
pipeline de features — inclusive `perfil_risco` e `fator_aplicado`, que só
existem porque este é um dataset sintético controlado; numa transação
real esses dados não existiriam.

## 5. Query de exemplo para montar a base de trabalho

```sql
SELECT
    f.id_transacao_natural,
    t.ano, t.mes, t.dia_semana, t.eh_dia_util,
    a.nome_area,
    c.nome_categoria, c.tipo_categoria,
    p.tipo_parceiro, p.rating_credito, p.prazo_medio,
    f.valor_bruto, f.valor_liquido, f.tipo_transacao,
    f.forma_pagamento, f.status_pagamento,
    g.flag_anomalia          -- só para avaliação, nunca como feature
FROM refined.fact_transacoes_financeiras f
JOIN refined.dim_tempo               t ON t.tempo_sk = f.tempo_sk
JOIN refined.dim_area                a ON a.area_sk = f.area_sk
JOIN refined.dim_categoria_contabil   c ON c.categoria_sk = f.categoria_sk
JOIN refined.dim_fornecedor_cliente   p ON p.parceiro_sk = f.parceiro_sk
LEFT JOIN ml.transacoes_gabarito      g ON g.id_transacao_raw = f.id_transacao_natural;
```

## 6. Responsabilidades e próximos passos

- **Engenharia de dados:** restante do pipeline (`fact_pagamentos`,
  `fact_recebimentos`, `fact_saldos_diarios`), testes automatizados e CI/CD.
- **Ciência de dados:** engenharia de atributos (a partir do que está
  pronto acima), modelo de detecção de anomalias, painel Power BI.
- **Conjunto:** engenharia de atributos que precise cruzar a análise de
  dados com ajustes no pipeline.

Pendências em `refined` que bloqueiem consumo devem ser reportadas para
priorização.
