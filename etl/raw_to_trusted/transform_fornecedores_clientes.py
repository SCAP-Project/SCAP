"""Transformacao raw -> trusted: raw.fornecedores_clientes -> trusted.fornecedores_clientes
(SCD Tipo 2).

Chave natural: trusted.id_parceiro_natural = raw.id_fornecedor_raw.

tipo_fornecedor, rating_credito e prazo_medio JA vem derivados do fluxo real
de transacoes/pagamentos/recebimentos -- o gerador sintetico
(dados_raw_fornecedores_clientes.py) fez essa agregacao uma vez, na origem.
Este script so copia, valida e versiona; nao recalcula nada.

Nomes de coluna diferem entre raw e trusted em alguns casos (cnpj_cpf ->
documento, contato -> contato_email, telefone -> contato_telefone), entao a
extracao normaliza para os nomes de trusted antes de comparar/inserir.

Mesma regra de versionamento das transformacoes anteriores (idempotente):
  - Parceiro nao existe em trusted           -> insere versao nova.
  - Existe e algum atributo monitorado mudou  -> fecha a versao atual e abre
                                                   uma nova (isto e esperado
                                                   com frequencia aqui: rating
                                                   de credito muda conforme o
                                                   comportamento observado).
  - Existe e nada mudou                       -> no-op.

Pre-requisito: sql/ddl/02_create_trusted_tables.sql aplicado.

Uso:
    python -m etl.raw_to_trusted.transform_fornecedores_clientes
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

# Atributos monitorados p/ SCD2 (ja nos nomes de trusted).
COLUNAS_VERSIONADAS = (
    "nome_fornecedor", "tipo_fornecedor", "documento", "contato_email",
    "contato_telefone", "endereco", "pais", "estado", "cidade",
    "setor_atuacao", "rating_credito", "prazo_medio",
)

RATINGS_VALIDOS = ("AAA", "AA", "A", "BBB", "BB", "B", "C", "SEM_HISTORICO")

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.fornecedores_clientes"

# DISTINCT ON + ORDER BY ingestion_ts DESC: fica com a linha mais recente por
# parceiro, caso raw tenha duplicata de id_fornecedor_raw.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_fornecedor_raw)
           id_fornecedor_raw, nome_fornecedor, tipo_fornecedor, cnpj_cpf,
           contato, telefone, endereco, pais, estado, cidade, setor_atuacao,
           rating_credito, prazo_medio, source_system
      FROM raw.fornecedores_clientes
     WHERE id_fornecedor_raw IS NOT NULL
       AND nome_fornecedor IS NOT NULL
       AND tipo_fornecedor IN ('CLIENTE', 'FORNECEDOR', 'AMBOS')
       AND (rating_credito IS NULL OR rating_credito = ANY(:ratings_validos))
     ORDER BY id_fornecedor_raw, ingestion_ts DESC
"""

SQL_ATUAIS_TRUSTED = """
    SELECT id_parceiro_natural, nome_fornecedor, tipo_fornecedor, documento,
           contato_email, contato_telefone, endereco, pais, estado, cidade,
           setor_atuacao, rating_credito, prazo_medio
      FROM trusted.fornecedores_clientes
     WHERE is_current = TRUE
"""

SQL_FECHAR_VERSAO = """
    UPDATE trusted.fornecedores_clientes
       SET is_current = FALSE,
           vigencia_fim = :hoje,
           atualizado_em = CURRENT_TIMESTAMP
     WHERE id_parceiro_natural = :id_natural
       AND is_current = TRUE
"""

SQL_INSERIR_VERSAO = """
    INSERT INTO trusted.fornecedores_clientes
        (id_parceiro_natural, nome_fornecedor, tipo_fornecedor, documento,
         contato_email, contato_telefone, endereco, pais, estado, cidade,
         setor_atuacao, rating_credito, prazo_medio,
         vigencia_inicio, is_current, etl_batch_id, source_system)
    VALUES
        (:id_parceiro_natural, :nome_fornecedor, :tipo_fornecedor, :documento,
         :contato_email, :contato_telefone, :endereco, :pais, :estado, :cidade,
         :setor_atuacao, :rating_credito, :prazo_medio,
         :hoje, TRUE, :batch_id, :source_system)
"""


def _normalizar(row) -> dict:
    """Mapeia a linha do raw pros nomes de coluna de trusted."""
    return {
        "id_parceiro_natural": row["id_fornecedor_raw"],
        "nome_fornecedor": row["nome_fornecedor"],
        "tipo_fornecedor": row["tipo_fornecedor"],
        "documento": row["cnpj_cpf"],
        "contato_email": row["contato"],
        "contato_telefone": row["telefone"],
        "endereco": row["endereco"],
        "pais": row["pais"],
        "estado": row["estado"],
        "cidade": row["cidade"],
        "setor_atuacao": row["setor_atuacao"],
        "rating_credito": row["rating_credito"],
        "prazo_medio": row["prazo_medio"],
        "source_system": row["source_system"],
    }


def _mudou(normalizado: dict, atual: dict) -> bool:
    return any(normalizado[coluna] != atual[coluna] for coluna in COLUNAS_VERSIONADAS)


def main() -> None:
    batch_id = uuid.uuid4()
    hoje = date.today()

    inseridas = versionadas = inalteradas = 0

    with get_connection() as conn:
        total_raw = conn.execute(text(SQL_TOTAL_RAW)).scalar_one()
        raw_rows = conn.execute(
            text(SQL_EXTRAIR_RAW), {"ratings_validos": list(RATINGS_VALIDOS)}
        ).mappings().all()
        if len(raw_rows) < total_raw:
            log.warning(
                "raw.fornecedores_clientes: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_fornecedor_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows), len(raw_rows), total_raw,
            )

        if not raw_rows:
            log.warning("raw.fornecedores_clientes nao tem nenhuma linha valida -- nada a transformar")
            return

        atuais = {r["id_parceiro_natural"]: r for r in conn.execute(text(SQL_ATUAIS_TRUSTED)).mappings()}

        for row in raw_rows:
            normalizado = _normalizar(row)
            id_natural = normalizado["id_parceiro_natural"]
            atual = atuais.get(id_natural)

            params = {**normalizado, "hoje": hoje, "batch_id": batch_id}

            if atual is None:
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                inseridas += 1
            elif _mudou(normalizado, atual):
                conn.execute(text(SQL_FECHAR_VERSAO), {"id_natural": id_natural, "hoje": hoje})
                conn.execute(text(SQL_INSERIR_VERSAO), params)
                versionadas += 1
            else:
                inalteradas += 1

    log.info(
        "raw.fornecedores_clientes -> trusted.fornecedores_clientes concluido: "
        "%d nova(s), %d versionada(s) (SCD2), %d inalterada(s)",
        inseridas, versionadas, inalteradas,
    )


if __name__ == "__main__":
    main()
