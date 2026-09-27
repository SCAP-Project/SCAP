"""Transformacao trusted -> refined: trusted.funcionarios -> refined.dim_funcionario.

area_sk precisa ser RESOLVIDO de novo: refined.dim_area tem chaves substitutas
proprias, diferentes de trusted.areas.area_sk. O caminho e
trusted.funcionarios.area_sk -> trusted.areas.id_area_natural (join) ->
refined.dim_area.area_sk (lookup pela versao vigente).

Fora isso, mesmo padrao das outras dimensoes: copia todo o historico de
trusted, UPSERT idempotente por (id_funcionario_natural, vigencia_inicio).

Esta dimensao nao se conecta a nenhum fato (a origem nao vincula funcionario
a transacao), entao nao bloqueia a modelagem -- e populada por completude do
star schema (analises de quadro/RH).

Pre-requisito: transform_funcionarios.py (trusted) e transform_dim_area.py
(refined) ja executados.

Uso:
    python -m etl.trusted_to_refined.transform_dim_funcionario
"""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

SQL_AREAS_REFINED_ATUAIS = "SELECT id_area_natural, area_sk FROM refined.dim_area WHERE is_current = TRUE"

# Join com trusted.areas resolve o id_area_natural de cada funcionario a
# partir do area_sk (que em trusted aponta pra trusted.areas, nao refined).
SQL_EXTRAIR_TRUSTED = """
    SELECT f.id_funcionario_natural, f.nome, f.cpf, f.cargo, a.id_area_natural,
           f.data_admissao, f.tipo_contrato, f.salario,
           f.vigencia_inicio, f.vigencia_fim, f.is_current, f.source_system
      FROM trusted.funcionarios f
      JOIN trusted.areas a ON a.area_sk = f.area_sk
"""

SQL_UPSERT = """
    INSERT INTO refined.dim_funcionario
        (id_funcionario_natural, nome, cpf, cargo, area_sk, data_admissao,
         tipo_contrato, salario, vigencia_inicio, vigencia_fim, is_current,
         etl_batch_id, source_system)
    VALUES %s
    ON CONFLICT (id_funcionario_natural, vigencia_inicio) DO UPDATE SET
        nome           = EXCLUDED.nome,
        cpf            = EXCLUDED.cpf,
        cargo          = EXCLUDED.cargo,
        area_sk        = EXCLUDED.area_sk,
        data_admissao  = EXCLUDED.data_admissao,
        tipo_contrato  = EXCLUDED.tipo_contrato,
        salario        = EXCLUDED.salario,
        vigencia_fim   = EXCLUDED.vigencia_fim,
        is_current     = EXCLUDED.is_current,
        etl_batch_id   = EXCLUDED.etl_batch_id,
        atualizado_em  = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_AREAS_REFINED_ATUAIS)
            areas_refined = dict(cur.fetchall())

            if not areas_refined:
                log.error("refined.dim_area esta vazia -- rode transform_dim_area.py antes")
                return

            cur.execute(SQL_EXTRAIR_TRUSTED)
            colunas = [c.name for c in cur.description]
            trusted_rows = [dict(zip(colunas, linha)) for linha in cur.fetchall()]

        if not trusted_rows:
            log.warning("trusted.funcionarios esta vazia -- rode transform_funcionarios.py antes")
            return

        linhas = []
        sem_area = 0
        for row in trusted_rows:
            area_sk = areas_refined.get(row["id_area_natural"])
            if area_sk is None:
                log.warning(
                    "Funcionario %s ignorado: area '%s' nao existe em refined.dim_area",
                    row["id_funcionario_natural"], row["id_area_natural"],
                )
                sem_area += 1
                continue

            linhas.append((
                row["id_funcionario_natural"], row["nome"], row["cpf"], row["cargo"], area_sk,
                row["data_admissao"], row["tipo_contrato"], row["salario"],
                row["vigencia_inicio"], row["vigencia_fim"], row["is_current"],
                batch_id, row["source_system"],
            ))

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas)

        raw_conn.commit()
        log.info(
            "trusted.funcionarios -> refined.dim_funcionario concluido: %d linha(s), %d sem area valida",
            len(linhas), sem_area,
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
