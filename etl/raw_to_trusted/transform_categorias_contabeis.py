"""Transformacao raw -> trusted: raw.categorias_contabeis -> trusted.categorias_contabeis
(SCD Tipo 2).

Chave natural: trusted.categorias_contabeis.id_categoria_natural =
str(raw.categorias_contabeis.id_categoria_raw). E o id numerico -- nao
codigo_contabil -- porque e o que raw.transacoes_financeiras.id_categoria_raw
referencia (ver dados_transacoes_financeiras.ipynb, coluna id_categoria_raw
sorteada de 1 a 40). Diferente de areas, aqui nao existe um "codigo" de
negocio separado do id.

Mesma regra de versionamento de transform_areas.py (idempotente):
  - Categoria nao existe em trusted           -> insere versao nova.
  - Existe e nome/tipo/codigo_contabil mudou   -> fecha a versao atual e
                                                    abre uma nova.
  - Existe e nada mudou                        -> no-op.

Pre-requisito: sql/ddl/02_create_trusted_tables.sql aplicado.

Uso:
    python -m etl.raw_to_trusted.transform_categorias_contabeis
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

# Atributos monitorados p/ SCD2: mudanca em qualquer um fecha a versao atual.
COLUNAS_VERSIONADAS = ("nome_categoria", "tipo_categoria", "codigo_contabil")

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.categorias_contabeis"

# DISTINCT ON + ORDER BY ingestion_ts DESC: se raw tiver mais de uma linha
# para o mesmo id_categoria_raw, fica com a mais recente. tipo_categoria e
# validado contra o dominio aceito por trusted (CHECK RECEITA/DESPESA).
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_categoria_raw)
           id_categoria_raw, nome_categoria, tipo_categoria, codigo_contabil, source_system
      FROM raw.categorias_contabeis
     WHERE id_categoria_raw IS NOT NULL
       AND nome_categoria IS NOT NULL
       AND codigo_contabil IS NOT NULL
       AND tipo_categoria IN ('RECEITA', 'DESPESA')
     ORDER BY id_categoria_raw, ingestion_ts DESC
"""

SQL_ATUAIS_TRUSTED = """
    SELECT id_categoria_natural, nome_categoria, tipo_categoria, codigo_contabil
      FROM trusted.categorias_contabeis
     WHERE is_current = TRUE
"""

SQL_FECHAR_VERSAO = """
    UPDATE trusted.categorias_contabeis
       SET is_current = FALSE,
           vigencia_fim = :hoje,
           atualizado_em = CURRENT_TIMESTAMP
     WHERE id_categoria_natural = :id_natural
       AND is_current = TRUE
"""

SQL_INSERIR_VERSAO = """
    INSERT INTO trusted.categorias_contabeis
        (id_categoria_natural, nome_categoria, tipo_categoria, codigo_contabil,
         vigencia_inicio, is_current, etl_batch_id, source_system)
    VALUES
        (:id_natural, :nome_categoria, :tipo_categoria, :codigo_contabil,
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
                "raw.categorias_contabeis: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_categoria_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows), len(raw_rows), total_raw,
            )

        if not raw_rows:
            log.warning("raw.categorias_contabeis nao tem nenhuma linha valida -- nada a transformar")
            return

        atuais = {r["id_categoria_natural"]: r for r in conn.execute(text(SQL_ATUAIS_TRUSTED)).mappings()}

        for row in raw_rows:
            id_natural = str(row["id_categoria_raw"])
            atual = atuais.get(id_natural)

            params = {
                "id_natural": id_natural,
                "nome_categoria": row["nome_categoria"],
                "tipo_categoria": row["tipo_categoria"],
                "codigo_contabil": row["codigo_contabil"],
                "hoje": hoje,
                "batch_id": batch_id,
                "source_system": row["source_system"],
            }

            if atual is None:
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                inseridas += 1
            elif _mudou(row, atual):
                conn.execute(text(SQL_FECHAR_VERSAO), {"id_natural": id_natural, "hoje": hoje})
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                versionadas += 1
            else:
                inalteradas += 1

    log.info(
        "raw.categorias_contabeis -> trusted.categorias_contabeis concluido: "
        "%d nova(s), %d versionada(s) (SCD2), %d inalterada(s)",
        inseridas, versionadas, inalteradas,
    )


if __name__ == "__main__":
    main()
