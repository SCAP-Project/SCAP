"""Carrega recebimentos em trusted por upsert e resolve transacao_sk e moeda_sk.

Requer as transações carregadas; recebimentos sem transação são ignorados com aviso."""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

TAMANHO_LOTE = 1000

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.recebimentos"

# Mantém a ingestão mais recente por recebimento.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_recebimento_raw)
           id_recebimento_raw, id_transacao_raw,
           data_recebimento::date AS data_recebimento,
           valor_recebido::numeric(18,2) AS valor_recebido,
           metodo_recebimento, comprovante, source_system
      FROM raw.recebimentos
     WHERE id_recebimento_raw IS NOT NULL
       AND id_transacao_raw IS NOT NULL
       AND data_recebimento IS NOT NULL
       AND metodo_recebimento IN ('PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'DEPOSITO', 'CHEQUE')
     ORDER BY id_recebimento_raw, ingestion_ts DESC
"""

SQL_TRANSACOES_ATUAIS = "SELECT id_transacao_natural, transacao_sk, moeda_sk FROM trusted.transacoes_financeiras"

SQL_UPSERT = """
    INSERT INTO trusted.recebimentos
        (id_recebimento_natural, transacao_sk, moeda_sk, data_recebimento, valor_recebido,
         metodo_recebimento, comprovante, etl_batch_id, source_system)
    VALUES %s
    ON CONFLICT (id_recebimento_natural) DO UPDATE SET
        transacao_sk       = EXCLUDED.transacao_sk,
        moeda_sk           = EXCLUDED.moeda_sk,
        data_recebimento   = EXCLUDED.data_recebimento,
        valor_recebido     = EXCLUDED.valor_recebido,
        metodo_recebimento = EXCLUDED.metodo_recebimento,
        comprovante        = EXCLUDED.comprovante,
        etl_batch_id       = EXCLUDED.etl_batch_id,
        atualizado_em      = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_TRANSACOES_ATUAIS)
            transacoes = {linha[0]: (linha[1], linha[2]) for linha in cur.fetchall()}

            if not transacoes:
                log.error(
                    "trusted.transacoes_financeiras esta vazia -- rode "
                    "transform_transacoes_financeiras.py antes"
                )
                return

            cur.execute(SQL_TOTAL_RAW)
            total_raw = cur.fetchone()[0]

            cur.execute(SQL_EXTRAIR_RAW)
            colunas = [c.name for c in cur.description]
            raw_rows = [dict(zip(colunas, linha)) for linha in cur.fetchall()]

        if len(raw_rows) < total_raw:
            log.warning(
                "raw.recebimentos: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_recebimento_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows),
                len(raw_rows),
                total_raw,
            )

        if not raw_rows:
            log.warning(
                "raw.recebimentos nao tem nenhuma linha valida -- nada a transformar"
            )
            return

        linhas = []
        sem_transacao = 0
        for row in raw_rows:
            chaves = transacoes.get(row["id_transacao_raw"])
            if chaves is None:
                log.warning(
                    "Recebimento %s ignorado: transacao '%s' nao existe em trusted.transacoes_financeiras",
                    row["id_recebimento_raw"],
                    row["id_transacao_raw"],
                )
                sem_transacao += 1
                continue
            transacao_sk, moeda_sk = chaves

            linhas.append(
                (
                    str(row["id_recebimento_raw"]),
                    transacao_sk,
                    moeda_sk,
                    row["data_recebimento"],
                    row["valor_recebido"],
                    row["metodo_recebimento"],
                    row["comprovante"],
                    batch_id,
                    row["source_system"],
                )
            )

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas, page_size=TAMANHO_LOTE)

        raw_conn.commit()
        log.info(
            "raw.recebimentos -> trusted.recebimentos concluido: "
            "%d linha(s) carregada(s) (upsert), %d ignorada(s) por transacao nao resolvida",
            len(linhas),
            sem_transacao,
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
