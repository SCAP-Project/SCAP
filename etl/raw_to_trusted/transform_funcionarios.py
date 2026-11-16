"""Versiona funcionários em trusted por SCD2 e resolve a área pelo departamento.

Requer as áreas carregadas; a chave natural é id_funcionario_raw."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

# Atributos que iniciam uma nova versão SCD2.
COLUNAS_VERSIONADAS = (
    "nome",
    "cpf",
    "cargo",
    "area_sk",
    "data_admissao",
    "tipo_contrato",
    "salario",
)

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.funcionarios"

# Mantém a ingestão mais recente por funcionário.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_funcionario_raw)
           id_funcionario_raw, nome, cpf, cargo, departamento,
           data_admissao::date AS data_admissao,
           salario::numeric(18,2) AS salario,
           tipo_contrato, source_system
      FROM raw.funcionarios
     WHERE id_funcionario_raw IS NOT NULL
       AND nome IS NOT NULL
       AND cpf IS NOT NULL
       AND cargo IS NOT NULL
       AND departamento IS NOT NULL
       AND tipo_contrato IN ('CLT', 'PJ', 'ESTAGIO', 'TEMPORARIO')
     ORDER BY id_funcionario_raw, ingestion_ts DESC
"""

SQL_AREAS_ATUAIS = """
    SELECT id_area_natural, area_sk FROM trusted.areas WHERE is_current = TRUE
"""

SQL_ATUAIS_TRUSTED = """
    SELECT id_funcionario_natural, nome, cpf, cargo, area_sk, data_admissao,
           tipo_contrato, salario
      FROM trusted.funcionarios
     WHERE is_current = TRUE
"""

SQL_FECHAR_VERSAO = """
    UPDATE trusted.funcionarios
       SET is_current = FALSE,
           vigencia_fim = :hoje,
           atualizado_em = CURRENT_TIMESTAMP
     WHERE id_funcionario_natural = :id_natural
       AND is_current = TRUE
"""

SQL_INSERIR_VERSAO = """
    INSERT INTO trusted.funcionarios
        (id_funcionario_natural, nome, cpf, cargo, area_sk, data_admissao,
         tipo_contrato, salario, vigencia_inicio, is_current, etl_batch_id, source_system)
    VALUES
        (:id_natural, :nome, :cpf, :cargo, :area_sk, :data_admissao,
         :tipo_contrato, :salario, :hoje, TRUE, :batch_id, :source_system)
"""


def _mudou(normalizado: dict, atual: dict) -> bool:
    return any(normalizado[coluna] != atual[coluna] for coluna in COLUNAS_VERSIONADAS)


def main() -> None:
    batch_id = uuid.uuid4()
    hoje = date.today()

    inseridas = versionadas = inalteradas = sem_area = 0

    with get_connection() as conn:
        areas_atuais = {
            r["id_area_natural"]: r["area_sk"]
            for r in conn.execute(text(SQL_AREAS_ATUAIS)).mappings()
        }
        if not areas_atuais:
            log.error(
                "trusted.areas nao tem nenhuma versao vigente -- rode transform_areas.py antes"
            )
            return

        total_raw = conn.execute(text(SQL_TOTAL_RAW)).scalar_one()
        raw_rows = conn.execute(text(SQL_EXTRAIR_RAW)).mappings().all()
        if len(raw_rows) < total_raw:
            log.warning(
                "raw.funcionarios: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_funcionario_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows),
                len(raw_rows),
                total_raw,
            )

        if not raw_rows:
            log.warning(
                "raw.funcionarios nao tem nenhuma linha valida -- nada a transformar"
            )
            return

        atuais = {
            r["id_funcionario_natural"]: r
            for r in conn.execute(text(SQL_ATUAIS_TRUSTED)).mappings()
        }

        for row in raw_rows:
            area_sk = areas_atuais.get(row["departamento"])
            if area_sk is None:
                log.warning(
                    "Funcionario %s ignorado: departamento '%s' nao existe em trusted.areas",
                    row["id_funcionario_raw"],
                    row["departamento"],
                )
                sem_area += 1
                continue

            id_natural = str(row["id_funcionario_raw"])
            normalizado = {
                "nome": row["nome"],
                "cpf": row["cpf"],
                "cargo": row["cargo"],
                "area_sk": area_sk,
                "data_admissao": row["data_admissao"],
                "tipo_contrato": row["tipo_contrato"],
                "salario": row["salario"],
            }
            atual = atuais.get(id_natural)

            params = {
                **normalizado,
                "id_natural": id_natural,
                "hoje": hoje,
                "batch_id": batch_id,
                "source_system": row["source_system"],
            }

            if atual is None:
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                inseridas += 1
            elif _mudou(normalizado, atual):
                conn.execute(
                    text(SQL_FECHAR_VERSAO), {"id_natural": id_natural, "hoje": hoje}
                )
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                versionadas += 1
            else:
                inalteradas += 1

    log.info(
        "raw.funcionarios -> trusted.funcionarios concluido: "
        "%d nova(s), %d versionada(s) (SCD2), %d inalterada(s), %d sem area valida",
        inseridas,
        versionadas,
        inalteradas,
        sem_area,
    )


if __name__ == "__main__":
    main()
