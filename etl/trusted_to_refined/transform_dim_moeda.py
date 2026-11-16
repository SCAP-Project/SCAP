"""Replica moedas em refined.dim_moeda, usando codigo_iso para o mapeamento."""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

SQL_EXTRAIR_TRUSTED = """
    SELECT codigo_iso, nome_moeda, simbolo, pais_referencia,
           vigencia_inicio, vigencia_fim, is_current, source_system
      FROM trusted.moedas
"""

SQL_UPSERT = """
    INSERT INTO refined.dim_moeda
        (codigo_iso, nome_moeda, simbolo, pais_referencia,
         vigencia_inicio, vigencia_fim, is_current, source_system, etl_batch_id)
    VALUES %s
    ON CONFLICT (codigo_iso) DO UPDATE SET
        nome_moeda      = EXCLUDED.nome_moeda,
        simbolo         = EXCLUDED.simbolo,
        pais_referencia = EXCLUDED.pais_referencia,
        vigencia_inicio = EXCLUDED.vigencia_inicio,
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
            log.warning("trusted.moedas esta vazia -- nada a transformar")
            return

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas)

        raw_conn.commit()
        log.info(
            "trusted.moedas -> refined.dim_moeda concluido: %d linha(s)", len(linhas)
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
