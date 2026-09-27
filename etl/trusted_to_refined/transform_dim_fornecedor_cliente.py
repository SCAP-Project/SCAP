"""Transformacao trusted -> refined: trusted.fornecedores_clientes -> refined.dim_fornecedor_cliente.

Mesmo padrao de transform_dim_area.py: chave substituta propria em refined,
de/para por chave natural (id_parceiro_natural), copia todo o historico de
trusted. Dois nomes de coluna mudam nesta camada: nome_fornecedor ->
nome_parceiro e tipo_fornecedor -> tipo_parceiro (mais generico, ja que o
mesmo parceiro pode ser CLIENTE, FORNECEDOR ou AMBOS).

UPSERT idempotente por (id_parceiro_natural, vigencia_inicio).

Pre-requisito: transform_fornecedores_clientes.py (camada trusted) ja executado.

Uso:
    python -m etl.trusted_to_refined.transform_dim_fornecedor_cliente
"""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

SQL_EXTRAIR_TRUSTED = """
    SELECT id_parceiro_natural, nome_fornecedor, tipo_fornecedor, documento,
           contato_email, contato_telefone, endereco, pais, estado, cidade,
           setor_atuacao, rating_credito, prazo_medio,
           vigencia_inicio, vigencia_fim, is_current, source_system
      FROM trusted.fornecedores_clientes
"""

SQL_UPSERT = """
    INSERT INTO refined.dim_fornecedor_cliente
        (id_parceiro_natural, nome_parceiro, tipo_parceiro, documento,
         contato_email, contato_telefone, endereco, pais, estado, cidade,
         setor_atuacao, rating_credito, prazo_medio,
         vigencia_inicio, vigencia_fim, is_current, source_system, etl_batch_id)
    VALUES %s
    ON CONFLICT (id_parceiro_natural, vigencia_inicio) DO UPDATE SET
        nome_parceiro    = EXCLUDED.nome_parceiro,
        tipo_parceiro    = EXCLUDED.tipo_parceiro,
        documento        = EXCLUDED.documento,
        contato_email    = EXCLUDED.contato_email,
        contato_telefone = EXCLUDED.contato_telefone,
        endereco         = EXCLUDED.endereco,
        pais             = EXCLUDED.pais,
        estado           = EXCLUDED.estado,
        cidade           = EXCLUDED.cidade,
        setor_atuacao    = EXCLUDED.setor_atuacao,
        rating_credito   = EXCLUDED.rating_credito,
        prazo_medio      = EXCLUDED.prazo_medio,
        vigencia_fim     = EXCLUDED.vigencia_fim,
        is_current       = EXCLUDED.is_current,
        etl_batch_id     = EXCLUDED.etl_batch_id,
        atualizado_em    = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_EXTRAIR_TRUSTED)
            linhas = [tuple(row) + (batch_id,) for row in cur.fetchall()]

        if not linhas:
            log.warning(
                "trusted.fornecedores_clientes esta vazia -- rode transform_fornecedores_clientes.py antes"
            )
            return

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas)

        raw_conn.commit()
        log.info(
            "trusted.fornecedores_clientes -> refined.dim_fornecedor_cliente concluido: %d linha(s)",
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
