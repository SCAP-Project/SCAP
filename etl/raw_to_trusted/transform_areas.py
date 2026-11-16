"""Versiona áreas em trusted por SCD2, usando codigo_area como chave natural.

Mudanças nos atributos fecham a versão atual e abrem outra; linhas iguais não mudam."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

# Atributos que iniciam uma nova versão SCD2.
COLUNAS_VERSIONADAS = ("nome_area", "gestor_responsavel", "email_gestor")

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.areas"

# Mantém a ingestão mais recente por chave natural.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (codigo_area)
           codigo_area, nome_area, gestor_responsavel, email_gestor, source_system
      FROM raw.areas
     WHERE codigo_area IS NOT NULL
       AND nome_area IS NOT NULL
     ORDER BY codigo_area, ingestion_ts DESC
"""

SQL_ATUAIS_TRUSTED = """
    SELECT id_area_natural, nome_area, gestor_responsavel, email_gestor
      FROM trusted.areas
     WHERE is_current = TRUE
"""

SQL_FECHAR_VERSAO = """
    UPDATE trusted.areas
       SET is_current = FALSE,
           vigencia_fim = :hoje,
           atualizado_em = CURRENT_TIMESTAMP
     WHERE id_area_natural = :codigo
       AND is_current = TRUE
"""

SQL_INSERIR_VERSAO = """
    INSERT INTO trusted.areas
        (id_area_natural, codigo_area, nome_area, gestor_responsavel, email_gestor,
         vigencia_inicio, is_current, etl_batch_id, source_system)
    VALUES
        (:codigo, :codigo, :nome_area, :gestor_responsavel, :email_gestor,
         :hoje, TRUE, :batch_id, :source_system)
"""


def _mudou(raw_row, atual: dict) -> bool:
    return any(raw_row[coluna] != atual[coluna] for coluna in COLUNAS_VERSIONADAS)


def main() -> None:
    batch_id = uuid.uuid4()
    hoje = date.today()

    inseridas = versionadas = inalteradas = 0

    with get_connection() as conn:
        total_raw = conn.execute(text(SQL_TOTAL_RAW)).scalar_one()
        raw_rows = conn.execute(text(SQL_EXTRAIR_RAW)).mappings().all()
        if len(raw_rows) < total_raw:
            log.warning(
                "raw.areas: %d linha(s) ignorada(s) por codigo_area/nome_area nulo ou duplicado (%d de %d validas)",
                total_raw - len(raw_rows),
                len(raw_rows),
                total_raw,
            )

        if not raw_rows:
            log.warning("raw.areas nao tem nenhuma linha valida -- nada a transformar")
            return

        atuais = {
            r["id_area_natural"]: r
            for r in conn.execute(text(SQL_ATUAIS_TRUSTED)).mappings()
        }

        for row in raw_rows:
            codigo = row["codigo_area"]
            atual = atuais.get(codigo)

            params = {
                "codigo": codigo,
                "nome_area": row["nome_area"],
                "gestor_responsavel": row["gestor_responsavel"],
                "email_gestor": row["email_gestor"],
                "hoje": hoje,
                "batch_id": batch_id,
                "source_system": row["source_system"],
            }

            if atual is None:
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                inseridas += 1
            elif _mudou(row, atual):
                conn.execute(text(SQL_FECHAR_VERSAO), {"codigo": codigo, "hoje": hoje})
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                versionadas += 1
            else:
                inalteradas += 1

    log.info(
        "raw.areas -> trusted.areas concluido: %d nova(s), %d versionada(s) (SCD2), %d inalterada(s)",
        inseridas,
        versionadas,
        inalteradas,
    )


if __name__ == "__main__":
    main()
