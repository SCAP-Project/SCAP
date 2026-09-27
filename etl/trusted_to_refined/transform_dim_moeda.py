"""Transformacao trusted -> refined: trusted.moedas -> refined.dim_moeda.

refined tem chaves substitutas PROPRIAS (nao reaproveita trusted.moeda_sk) --
o de/para entre as duas camadas e sempre por chave natural (codigo_iso).

refined.dim_moeda.codigo_iso e UNIQUE sozinho (nao par com vigencia_inicio
como as outras dimensoes), entao aqui so existe uma versao por moeda mesmo
com as colunas de SCD2 presentes na tabela. Copia todas as colunas de
trusted (nao so is_current=TRUE) para refined ficar espelhado com a origem.

UPSERT idempotente por codigo_iso.

Pre-requisito: seed_moedas.py (camada trusted) ja executado.

Uso:
    python -m etl.trusted_to_refined.transform_dim_moeda
"""

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
        log.info("trusted.moedas -> refined.dim_moeda concluido: %d linha(s)", len(linhas))
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
