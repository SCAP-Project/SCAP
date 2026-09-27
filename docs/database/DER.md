# DER — Diagrama de Entidade-Relacionamento

> Substitui os diagramas da seção 5 de `DataWarehouse_Documentacao.pdf/docx`,
> que documentam uma versão anterior do schema (ainda tinham `funcionario_sk`
> nas fatos, `status_pagamento` em `Pago/Pendente/Cancelado`, e não incluíam
> `trusted.moedas` nem o schema `ml`). Este arquivo reflete o schema
> efetivamente aplicado no RDS em 27/09/2026. Colunas de auditoria padrão
> (`etl_batch_id`, `criado_em`, `atualizado_em`, `source_system`) foram
> omitidas dos diagramas por clareza — estão listadas no dicionário de dados
> (`GUIA_REFINED_PARA_ML.md` e `DataWarehouse_Documentacao`).

## Camada TRUSTED (Silver)

```mermaid
erDiagram
    MOEDAS {
        bigint moeda_sk PK
        char_3 codigo_iso UK
        text nome_moeda
    }
    AREAS {
        bigint area_sk PK
        text id_area_natural UK
        text codigo_area
        text nome_area
        boolean is_current
    }
    CATEGORIAS_CONTABEIS {
        bigint categoria_sk PK
        text id_categoria_natural UK
        text nome_categoria
        text tipo_categoria
        boolean is_current
    }
    FORNECEDORES_CLIENTES {
        bigint parceiro_sk PK
        text id_parceiro_natural UK
        text nome_fornecedor
        text tipo_fornecedor
        text rating_credito
        int prazo_medio
        boolean is_current
    }
    FUNCIONARIOS {
        bigint funcionario_sk PK
        text id_funcionario_natural UK
        bigint area_sk FK
        text nome
        text tipo_contrato
        boolean is_current
    }
    TRANSACOES_FINANCEIRAS {
        bigint transacao_sk PK
        text id_transacao_natural UK
        bigint area_sk FK
        bigint parceiro_sk FK
        bigint categoria_sk FK
        bigint moeda_sk FK
        decimal valor_bruto
        decimal valor_liquido
        text tipo_transacao
        text status_pagamento
    }
    PAGAMENTOS {
        bigint pagamento_sk PK
        text id_pagamento_natural UK
        bigint transacao_sk FK
        bigint moeda_sk FK
        decimal valor_pago
    }
    RECEBIMENTOS {
        bigint recebimento_sk PK
        text id_recebimento_natural UK
        bigint transacao_sk FK
        bigint moeda_sk FK
        decimal valor_recebido
    }

    AREAS ||--o{ FUNCIONARIOS : "area_sk"
    AREAS ||--o{ TRANSACOES_FINANCEIRAS : "area_sk"
    FORNECEDORES_CLIENTES ||--o{ TRANSACOES_FINANCEIRAS : "parceiro_sk"
    CATEGORIAS_CONTABEIS ||--o{ TRANSACOES_FINANCEIRAS : "categoria_sk"
    MOEDAS ||--o{ TRANSACOES_FINANCEIRAS : "moeda_sk"
    TRANSACOES_FINANCEIRAS ||--o{ PAGAMENTOS : "transacao_sk"
    TRANSACOES_FINANCEIRAS ||--o{ RECEBIMENTOS : "transacao_sk"
    MOEDAS ||--o{ PAGAMENTOS : "moeda_sk"
    MOEDAS ||--o{ RECEBIMENTOS : "moeda_sk"
```

Nota: `PAGAMENTOS`/`RECEBIMENTOS` não têm `parceiro_sk` próprio em
`trusted` — o parceiro é sempre resolvido via `transacao_sk`. Isso muda em
`refined` (ver abaixo).

## Camada REFINED (Gold) — Star Schema

```mermaid
erDiagram
    DIM_TEMPO {
        bigint tempo_sk PK
        date data UK
        int ano
        int mes
        boolean eh_dia_util
        boolean eh_feriado
    }
    DIM_MOEDA {
        bigint moeda_sk PK
        char_3 codigo_iso UK
    }
    DIM_AREA {
        bigint area_sk PK
        text id_area_natural UK
        boolean is_current
    }
    DIM_CATEGORIA_CONTABIL {
        bigint categoria_sk PK
        text id_categoria_natural UK
        text tipo_categoria
        boolean is_current
    }
    DIM_FORNECEDOR_CLIENTE {
        bigint parceiro_sk PK
        text id_parceiro_natural UK
        text tipo_parceiro
        text rating_credito
        int prazo_medio
        boolean is_current
    }
    DIM_FUNCIONARIO {
        bigint funcionario_sk PK
        text id_funcionario_natural UK
        bigint area_sk FK
        boolean is_current
    }
    FACT_TRANSACOES_FINANCEIRAS {
        bigint transacao_sk PK
        text id_transacao_natural UK
        bigint tempo_sk FK
        bigint area_sk FK
        bigint parceiro_sk FK
        bigint categoria_sk FK
        bigint moeda_sk FK
        decimal valor_bruto
        decimal valor_liquido
        text status_pagamento
    }
    FACT_PAGAMENTOS {
        bigint pagamento_sk PK
        text id_pagamento_natural UK
        bigint tempo_sk FK
        bigint transacao_sk FK
        bigint parceiro_sk FK
        bigint moeda_sk FK
        decimal valor_pago
    }
    FACT_RECEBIMENTOS {
        bigint recebimento_sk PK
        text id_recebimento_natural UK
        bigint tempo_sk FK
        bigint transacao_sk FK
        bigint parceiro_sk FK
        bigint moeda_sk FK
        decimal valor_recebido
    }
    FACT_SALDOS_DIARIOS {
        bigint saldo_sk PK
        bigint tempo_sk FK
        bigint area_sk FK
        bigint moeda_sk FK
        decimal saldo_inicial
        decimal saldo_final
    }

    DIM_TEMPO ||--o{ FACT_TRANSACOES_FINANCEIRAS : tempo_sk
    DIM_AREA ||--o{ FACT_TRANSACOES_FINANCEIRAS : area_sk
    DIM_FORNECEDOR_CLIENTE ||--o{ FACT_TRANSACOES_FINANCEIRAS : parceiro_sk
    DIM_CATEGORIA_CONTABIL ||--o{ FACT_TRANSACOES_FINANCEIRAS : categoria_sk
    DIM_MOEDA ||--o{ FACT_TRANSACOES_FINANCEIRAS : moeda_sk

    DIM_TEMPO ||--o{ FACT_PAGAMENTOS : tempo_sk
    FACT_TRANSACOES_FINANCEIRAS ||--o{ FACT_PAGAMENTOS : transacao_sk
    DIM_FORNECEDOR_CLIENTE ||--o{ FACT_PAGAMENTOS : "parceiro_sk (herdado da transacao)"
    DIM_MOEDA ||--o{ FACT_PAGAMENTOS : moeda_sk

    DIM_TEMPO ||--o{ FACT_RECEBIMENTOS : tempo_sk
    FACT_TRANSACOES_FINANCEIRAS ||--o{ FACT_RECEBIMENTOS : transacao_sk
    DIM_FORNECEDOR_CLIENTE ||--o{ FACT_RECEBIMENTOS : "parceiro_sk (herdado da transacao)"
    DIM_MOEDA ||--o{ FACT_RECEBIMENTOS : moeda_sk

    DIM_TEMPO ||--o{ FACT_SALDOS_DIARIOS : tempo_sk
    DIM_AREA ||--o{ FACT_SALDOS_DIARIOS : area_sk
    DIM_MOEDA ||--o{ FACT_SALDOS_DIARIOS : moeda_sk

    DIM_AREA ||--o{ DIM_FUNCIONARIO : "area_sk (nao conecta a fatos)"
```

**Status de implementação (27/09/2026):** `dim_tempo`, `dim_moeda`,
`dim_area`, `dim_categoria_contabil`, `dim_fornecedor_cliente`,
`dim_funcionario` e `fact_transacoes_financeiras` estão populadas.
`fact_pagamentos`, `fact_recebimentos` e `fact_saldos_diarios` estão
desenhadas aqui mas **ainda não implementadas** — os scripts de
`trusted_to_refined` pra elas ainda não foram escritos.

## Gabarito de anomalias (fora do Medallion)

`ml.transacoes_gabarito` não tem FK real com nenhuma tabela — é join
analítico por chave natural, só para avaliação de modelo:

```mermaid
erDiagram
    FACT_TRANSACOES_FINANCEIRAS {
        text id_transacao_natural UK
    }
    TRANSACOES_GABARITO {
        text id_transacao_raw PK
        boolean flag_anomalia
        text perfil_risco
    }
    FACT_TRANSACOES_FINANCEIRAS ||..o{ TRANSACOES_GABARITO : "id_transacao_natural = id_transacao_raw (join analitico, sem FK)"
```
