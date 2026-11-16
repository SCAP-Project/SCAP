"""Carrega a fato financeira em refined por upsert em lote.

Mapeia as dimensões pelas chaves naturais, pois trusted e refined têm
sequências independentes. Resolve tempo_sk pela data da transação."""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

TAMANHO_LOTE = 1000

# Recupera as chaves naturais para mapear dimensões entre camadas.
SQL_EXTRAIR_TRUSTED = """
    SELECT t.id_transacao_natural, t.data_transacao, t.valor_bruto, t.valor_liquido,
           t.tipo_transacao, t.forma_pagamento, t.status_pagamento, t.source_system,
           a.id_area_natural, p.id_parceiro_natural, c.id_categoria_natural, m.codigo_iso
      FROM trusted.transacoes_financeiras t
      JOIN trusted.areas a                  ON a.area_sk = t.area_sk
      JOIN trusted.fornecedores_clientes p  ON p.parceiro_sk = t.parceiro_sk
      JOIN trusted.categorias_contabeis c   ON c.categoria_sk = t.categoria_sk
      JOIN trusted.moedas m                 ON m.moeda_sk = t.moeda_sk
"""

SQL_AREAS_REFINED = (
    "SELECT id_area_natural, area_sk FROM refined.dim_area WHERE is_current = TRUE"
)
SQL_PARCEIROS_REFINED = "SELECT id_parceiro_natural, parceiro_sk FROM refined.dim_fornecedor_cliente WHERE is_current = TRUE"
SQL_CATEGORIAS_REFINED = "SELECT id_categoria_natural, categoria_sk FROM refined.dim_categoria_contabil WHERE is_current = TRUE"
SQL_MOEDAS_REFINED = (
    "SELECT codigo_iso, moeda_sk FROM refined.dim_moeda WHERE is_current = TRUE"
)
SQL_TEMPO_REFINED = "SELECT data, tempo_sk FROM refined.dim_tempo"

SQL_UPSERT = """
    INSERT INTO refined.fact_transacoes_financeiras
        (id_transacao_natural, tempo_sk, area_sk, parceiro_sk, categoria_sk, moeda_sk,
         valor_bruto, valor_liquido, tipo_transacao, forma_pagamento, status_pagamento,
         source_system, etl_batch_id)
    VALUES %s
    ON CONFLICT (id_transacao_natural) DO UPDATE SET
        tempo_sk         = EXCLUDED.tempo_sk,
        area_sk          = EXCLUDED.area_sk,
        parceiro_sk      = EXCLUDED.parceiro_sk,
        categoria_sk     = EXCLUDED.categoria_sk,
        moeda_sk         = EXCLUDED.moeda_sk,
        valor_bruto      = EXCLUDED.valor_bruto,
        valor_liquido    = EXCLUDED.valor_liquido,
        tipo_transacao   = EXCLUDED.tipo_transacao,
        forma_pagamento  = EXCLUDED.forma_pagamento,
        status_pagamento = EXCLUDED.status_pagamento,
        etl_batch_id     = EXCLUDED.etl_batch_id,
        atualizado_em    = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_AREAS_REFINED)
            areas = dict(cur.fetchall())
            cur.execute(SQL_PARCEIROS_REFINED)
            parceiros = dict(cur.fetchall())
            cur.execute(SQL_CATEGORIAS_REFINED)
            categorias = dict(cur.fetchall())
            cur.execute(SQL_MOEDAS_REFINED)
            moedas = dict(cur.fetchall())
            cur.execute(SQL_TEMPO_REFINED)
            tempos = dict(cur.fetchall())

            if not (areas and parceiros and categorias and moedas and tempos):
                log.error(
                    "Dimensoes de refined incompletas (areas=%d, parceiros=%d, categorias=%d, "
                    "moedas=%d, tempo=%d) -- rode as transformacoes/seeds de dimensao antes",
                    len(areas),
                    len(parceiros),
                    len(categorias),
                    len(moedas),
                    len(tempos),
                )
                return

            cur.execute(SQL_EXTRAIR_TRUSTED)
            colunas = [c.name for c in cur.description]
            trusted_rows = [dict(zip(colunas, linha)) for linha in cur.fetchall()]

        if not trusted_rows:
            log.warning(
                "trusted.transacoes_financeiras nao retornou linhas -- rode "
                "transform_transacoes_financeiras.py (raw->trusted) antes"
            )
            return

        linhas = []
        sem_dimensao = 0
        for row in trusted_rows:
            tempo_sk = tempos.get(row["data_transacao"])
            area_sk = areas.get(row["id_area_natural"])
            parceiro_sk = parceiros.get(row["id_parceiro_natural"])
            categoria_sk = categorias.get(row["id_categoria_natural"])
            moeda_sk = moedas.get(row["codigo_iso"])

            if None in (tempo_sk, area_sk, parceiro_sk, categoria_sk, moeda_sk):
                log.warning(
                    "Transacao %s ignorada: dimensao nao resolvida "
                    "(tempo=%s, area=%s, parceiro=%s, categoria=%s, moeda=%s)",
                    row["id_transacao_natural"],
                    tempo_sk,
                    area_sk,
                    parceiro_sk,
                    categoria_sk,
                    moeda_sk,
                )
                sem_dimensao += 1
                continue

            linhas.append(
                (
                    row["id_transacao_natural"],
                    tempo_sk,
                    area_sk,
                    parceiro_sk,
                    categoria_sk,
                    moeda_sk,
                    row["valor_bruto"],
                    row["valor_liquido"],
                    row["tipo_transacao"],
                    row["forma_pagamento"],
                    row["status_pagamento"],
                    row["source_system"],
                    batch_id,
                )
            )

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas, page_size=TAMANHO_LOTE)

        raw_conn.commit()
        log.info(
            "trusted.transacoes_financeiras -> refined.fact_transacoes_financeiras concluido: "
            "%d linha(s) carregada(s) (upsert), %d ignorada(s) por dimensao nao resolvida",
            len(linhas),
            sem_dimensao,
        )
    except Exception:
        raw_conn.rollback()
        log.exception(
            "Falha na transformacao -- rollback aplicado, nada foi persistido"
        )
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
