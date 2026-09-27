"""Transformacao raw -> trusted: raw.transacoes_financeiras -> trusted.transacoes_financeiras.

Resolve 4 chaves estrangeiras por lookup em memoria (as dimensoes sao
pequenas -- no maximo poucas centenas de linhas -- entao carregar cada uma
inteira uma vez e mais barato que uma query por transacao):
  - codigo_area_raw    -> trusted.areas.id_area_natural                     -> area_sk
  - id_fornecedor_raw  -> trusted.fornecedores_clientes.id_parceiro_natural -> parceiro_sk
  - id_categoria_raw   -> trusted.categorias_contabeis.id_categoria_natural -> categoria_sk
  - moeda              -> trusted.moedas.codigo_iso                        -> moeda_sk

Diferente das dimensoes (areas, categorias, fornecedores, funcionarios),
trusted.transacoes_financeiras NAO tem SCD Tipo 2 -- e fato, nao dimensao.
E um UPSERT simples por id_transacao_natural (INSERT ... ON CONFLICT DO
UPDATE), feito em lote com psycopg2.extras.execute_values: com 40k+ linhas,
um INSERT por linha seria dezenas de minutos so em latencia de rede ate o
RDS (via tunel SSH); em lotes de 1000, sao poucas dezenas de round-trips.

Pre-requisito: transform_areas.py, transform_categorias_contabeis.py,
transform_fornecedores_clientes.py e seed_moedas.py ja executados.

Uso:
    python -m etl.raw_to_trusted.transform_transacoes_financeiras
"""

from __future__ import annotations

import re
import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

TAMANHO_LOTE = 1000

_ESPACOS_MULTIPLOS = re.compile(r"\s+")


def _limpar_descricao(texto: str) -> str:
    """Colapsa espacos repetidos e remove espaco nas pontas."""
    return _ESPACOS_MULTIPLOS.sub(" ", texto.strip())


SQL_TOTAL_RAW = "SELECT count(*) FROM raw.transacoes_financeiras"

# DISTINCT ON + ORDER BY ingestion_ts DESC: fica com a linha mais recente por
# transacao, caso raw tenha duplicata de id_transacao_raw.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_transacao_raw)
           id_transacao_raw,
           data_transacao::date AS data_transacao,
           data_competencia::date AS data_competencia,
           codigo_area_raw,
           id_fornecedor_raw,
           tipo_transacao,
           valor_bruto::numeric(18,2) AS valor_bruto,
           valor_liquido::numeric(18,2) AS valor_liquido,
           moeda,
           descricao,
           id_categoria_raw,
           forma_pagamento,
           status_pagamento,
           source_system
      FROM raw.transacoes_financeiras
     WHERE id_transacao_raw IS NOT NULL
       AND data_transacao IS NOT NULL
       AND data_competencia IS NOT NULL
       AND codigo_area_raw IS NOT NULL
       AND id_fornecedor_raw IS NOT NULL
       AND id_categoria_raw IS NOT NULL
       AND descricao IS NOT NULL
       AND tipo_transacao IN ('RECEITA', 'DESPESA')
       AND forma_pagamento IN ('PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO')
       AND status_pagamento IN ('PAGO', 'ATRASADO', 'CANCELADO')
     ORDER BY id_transacao_raw, ingestion_ts DESC
"""

SQL_AREAS_ATUAIS = "SELECT id_area_natural, area_sk FROM trusted.areas WHERE is_current = TRUE"
SQL_PARCEIROS_ATUAIS = (
    "SELECT id_parceiro_natural, parceiro_sk FROM trusted.fornecedores_clientes WHERE is_current = TRUE"
)
SQL_CATEGORIAS_ATUAIS = (
    "SELECT id_categoria_natural, categoria_sk FROM trusted.categorias_contabeis WHERE is_current = TRUE"
)
SQL_MOEDAS_ATUAIS = "SELECT codigo_iso, moeda_sk FROM trusted.moedas WHERE is_current = TRUE"

SQL_UPSERT = """
    INSERT INTO trusted.transacoes_financeiras
        (id_transacao_natural, area_sk, parceiro_sk, categoria_sk, moeda_sk,
         data_transacao, data_competencia, valor_bruto, valor_liquido,
         tipo_transacao, forma_pagamento, status_pagamento, descricao_limpa,
         etl_batch_id, source_system)
    VALUES %s
    ON CONFLICT (id_transacao_natural) DO UPDATE SET
        area_sk          = EXCLUDED.area_sk,
        parceiro_sk      = EXCLUDED.parceiro_sk,
        categoria_sk     = EXCLUDED.categoria_sk,
        moeda_sk         = EXCLUDED.moeda_sk,
        data_transacao   = EXCLUDED.data_transacao,
        data_competencia = EXCLUDED.data_competencia,
        valor_bruto      = EXCLUDED.valor_bruto,
        valor_liquido    = EXCLUDED.valor_liquido,
        tipo_transacao   = EXCLUDED.tipo_transacao,
        forma_pagamento  = EXCLUDED.forma_pagamento,
        status_pagamento = EXCLUDED.status_pagamento,
        descricao_limpa  = EXCLUDED.descricao_limpa,
        etl_batch_id     = EXCLUDED.etl_batch_id,
        atualizado_em    = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_AREAS_ATUAIS)
            areas = dict(cur.fetchall())
            cur.execute(SQL_PARCEIROS_ATUAIS)
            parceiros = dict(cur.fetchall())
            cur.execute(SQL_CATEGORIAS_ATUAIS)
            categorias = dict(cur.fetchall())
            cur.execute(SQL_MOEDAS_ATUAIS)
            moedas = dict(cur.fetchall())

            if not (areas and parceiros and categorias and moedas):
                log.error(
                    "Dimensoes de apoio incompletas (areas=%d, parceiros=%d, categorias=%d, moedas=%d) "
                    "-- rode as transformacoes de dimensao antes",
                    len(areas), len(parceiros), len(categorias), len(moedas),
                )
                return

            cur.execute(SQL_TOTAL_RAW)
            total_raw = cur.fetchone()[0]

            cur.execute(SQL_EXTRAIR_RAW)
            colunas = [c.name for c in cur.description]
            raw_rows = [dict(zip(colunas, linha)) for linha in cur.fetchall()]

        if len(raw_rows) < total_raw:
            log.warning(
                "raw.transacoes_financeiras: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_transacao_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows), len(raw_rows), total_raw,
            )

        if not raw_rows:
            log.warning("raw.transacoes_financeiras nao tem nenhuma linha valida -- nada a transformar")
            return

        linhas = []
        sem_dimensao = 0
        for row in raw_rows:
            area_sk = areas.get(row["codigo_area_raw"])
            parceiro_sk = parceiros.get(row["id_fornecedor_raw"])
            categoria_sk = categorias.get(row["id_categoria_raw"])
            moeda_sk = moedas.get(row["moeda"])

            if None in (area_sk, parceiro_sk, categoria_sk, moeda_sk):
                log.warning(
                    "Transacao %s ignorada: dimensao nao resolvida "
                    "(area=%s, parceiro=%s, categoria=%s, moeda=%s)",
                    row["id_transacao_raw"], area_sk, parceiro_sk, categoria_sk, moeda_sk,
                )
                sem_dimensao += 1
                continue

            linhas.append((
                row["id_transacao_raw"], area_sk, parceiro_sk, categoria_sk, moeda_sk,
                row["data_transacao"], row["data_competencia"],
                row["valor_bruto"], row["valor_liquido"],
                row["tipo_transacao"], row["forma_pagamento"], row["status_pagamento"],
                _limpar_descricao(row["descricao"]),
                batch_id, row["source_system"],
            ))

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas, page_size=TAMANHO_LOTE)

        raw_conn.commit()
        log.info(
            "raw.transacoes_financeiras -> trusted.transacoes_financeiras concluido: "
            "%d linha(s) carregada(s) (upsert), %d ignorada(s) por dimensao nao resolvida",
            len(linhas), sem_dimensao,
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
