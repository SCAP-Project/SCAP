"""Transformacao trusted -> refined: trusted.categorias_contabeis -> refined.dim_categoria_contabil.

Mesmo padrao de transform_dim_area.py: chave substituta propria em refined,
de/para por chave natural (id_categoria_natural), copia todo o historico de
trusted. UPSERT idempotente por (id_categoria_natural, vigencia_inicio).

Pre-requisito: transform_categorias_contabeis.py (camada trusted) ja executado.

Uso:
    python -m etl.trusted_to_refined.transform_dim_categoria_contabil
"""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

SQL_EXTRAIR_TRUSTED = """
    SELECT id_categoria_natural, nome_categoria, tipo_categoria, codigo_contabil,
           vigencia_inicio, vigencia_fim, is_current, source_system
      FROM trusted.categorias_contabeis
"""

SQL_UPSERT = """
    INSERT INTO refined.dim_categoria_contabil
        (id_categoria_natural, nome_categoria, tipo_categoria, codigo_contabil,
         vigencia_inicio, vigencia_fim, is_current, source_system, etl_batch_id)
    VALUES %s
    ON CONFLICT (id_categoria_natural, vigencia_inicio) DO UPDATE SET
        nome_categoria  = EXCLUDED.nome_categoria,
        tipo_categoria  = EXCLUDED.tipo_categoria,
        codigo_contabil = EXCLUDED.codigo_contabil,
        vigencia_fim    = EXCLUDED.vigencia_fim,
        is_current      = EXCLUDED.is_current,
        etl_batch_id    = EXCLUDED.etl_batch_id,
        atualizado_em   = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_EXTRAIR_TRUSTED)
            linhas = [tuple(row) + (batch_id,) for row in cur.fetchall()]

        if not linhas:
            log.warning("trusted.categorias_contabeis esta vazia -- rode transform_categorias_contabeis.py antes")
            return

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas)

        raw_conn.commit()
        log.info(
            "trusted.categorias_contabeis -> refined.dim_categoria_contabil concluido: %d linha(s)",
            len(linhas),
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
