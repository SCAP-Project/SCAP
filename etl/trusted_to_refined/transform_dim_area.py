"""Transformacao trusted -> refined: trusted.areas -> refined.dim_area.

refined tem chaves substitutas PROPRIAS (nao reaproveita trusted.area_sk) --
o de/para entre camadas e sempre por chave natural (id_area_natural). Copia
TODAS as versoes de trusted (nao so is_current=TRUE), preservando o
historico de SCD2 tambem em refined.

UPSERT idempotente por (id_area_natural, vigencia_inicio).

Pre-requisito: transform_areas.py (camada trusted) ja executado.

Uso:
    python -m etl.trusted_to_refined.transform_dim_area
"""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

SQL_EXTRAIR_TRUSTED = """
    SELECT id_area_natural, codigo_area, nome_area, gestor_responsavel, email_gestor,
           vigencia_inicio, vigencia_fim, is_current, source_system
      FROM trusted.areas
"""

SQL_UPSERT = """
    INSERT INTO refined.dim_area
        (id_area_natural, codigo_area, nome_area, gestor_responsavel, email_gestor,
         vigencia_inicio, vigencia_fim, is_current, source_system, etl_batch_id)
    VALUES %s
    ON CONFLICT (id_area_natural, vigencia_inicio) DO UPDATE SET
        codigo_area        = EXCLUDED.codigo_area,
        nome_area          = EXCLUDED.nome_area,
        gestor_responsavel = EXCLUDED.gestor_responsavel,
        email_gestor       = EXCLUDED.email_gestor,
        vigencia_fim       = EXCLUDED.vigencia_fim,
        is_current         = EXCLUDED.is_current,
        etl_batch_id       = EXCLUDED.etl_batch_id,
        atualizado_em      = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_EXTRAIR_TRUSTED)
            linhas = [tuple(row) + (batch_id,) for row in cur.fetchall()]

        if not linhas:
            log.warning("trusted.areas esta vazia -- rode transform_areas.py antes")
            return

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas)

        raw_conn.commit()
        log.info("trusted.areas -> refined.dim_area concluido: %d linha(s)", len(linhas))
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
