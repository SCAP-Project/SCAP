"""Transformacao raw -> trusted: raw.pagamentos -> trusted.pagamentos.

raw.pagamentos nao tem coluna de moeda -- moeda_sk e HERDADO da transacao-pai
(mesmo padrao usado em refined.fact_pagamentos): resolve-se transacao_sk e
moeda_sk juntos, num unico lookup em trusted.transacoes_financeiras por
id_transacao_raw.

Assim como transacoes_financeiras, esta tabela NAO tem SCD Tipo 2 -- e fato.
UPSERT em lote por id_pagamento_natural (INSERT ... ON CONFLICT DO UPDATE via
psycopg2.extras.execute_values), pelo mesmo motivo de performance de
transform_transacoes_financeiras.py (dezenas de milhares de linhas).

Pre-requisito: transform_transacoes_financeiras.py ja executado (e quem
popula a tabela de onde este script resolve transacao_sk/moeda_sk).

Uso:
    python -m etl.raw_to_trusted.transform_pagamentos
"""

from __future__ import annotations

import uuid

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

TAMANHO_LOTE = 1000

SQL_TOTAL_RAW = "SELECT count(*) FROM raw.pagamentos"

# DISTINCT ON + ORDER BY ingestion_ts DESC: fica com a linha mais recente por
# pagamento, caso raw tenha duplicata de id_pagamento_raw.
SQL_EXTRAIR_RAW = """
    SELECT DISTINCT ON (id_pagamento_raw)
           id_pagamento_raw, id_transacao_raw,
           data_pagamento::date AS data_pagamento,
           valor_pago::numeric(18,2) AS valor_pago,
           metodo_pagamento, comprovante, source_system
      FROM raw.pagamentos
     WHERE id_pagamento_raw IS NOT NULL
       AND id_transacao_raw IS NOT NULL
       AND data_pagamento IS NOT NULL
       AND metodo_pagamento IN ('PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO')
     ORDER BY id_pagamento_raw, ingestion_ts DESC
"""

SQL_TRANSACOES_ATUAIS = "SELECT id_transacao_natural, transacao_sk, moeda_sk FROM trusted.transacoes_financeiras"

SQL_UPSERT = """
    INSERT INTO trusted.pagamentos
        (id_pagamento_natural, transacao_sk, moeda_sk, data_pagamento, valor_pago,
         metodo_pagamento, comprovante, etl_batch_id, source_system)
    VALUES %s
    ON CONFLICT (id_pagamento_natural) DO UPDATE SET
        transacao_sk     = EXCLUDED.transacao_sk,
        moeda_sk         = EXCLUDED.moeda_sk,
        data_pagamento   = EXCLUDED.data_pagamento,
        valor_pago       = EXCLUDED.valor_pago,
        metodo_pagamento = EXCLUDED.metodo_pagamento,
        comprovante      = EXCLUDED.comprovante,
        etl_batch_id     = EXCLUDED.etl_batch_id,
        atualizado_em    = CURRENT_TIMESTAMP
"""


def main() -> None:
    batch_id = str(uuid.uuid4())

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            cur.execute(SQL_TRANSACOES_ATUAIS)
            # id_transacao_natural -> (transacao_sk, moeda_sk)
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
                "raw.pagamentos: %d linha(s) ignorada(s) por campo nulo/invalido "
                "ou id_pagamento_raw duplicado (%d de %d validas)",
                total_raw - len(raw_rows), len(raw_rows), total_raw,
            )

        if not raw_rows:
            log.warning("raw.pagamentos nao tem nenhuma linha valida -- nada a transformar")
            return

        linhas = []
        sem_transacao = 0
        for row in raw_rows:
            chaves = transacoes.get(row["id_transacao_raw"])
            if chaves is None:
                log.warning(
                    "Pagamento %s ignorado: transacao '%s' nao existe em trusted.transacoes_financeiras",
                    row["id_pagamento_raw"], row["id_transacao_raw"],
                )
                sem_transacao += 1
                continue
            transacao_sk, moeda_sk = chaves

            linhas.append((
                str(row["id_pagamento_raw"]), transacao_sk, moeda_sk,
                row["data_pagamento"], row["valor_pago"], row["metodo_pagamento"],
                row["comprovante"], batch_id, row["source_system"],
            ))

        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas, page_size=TAMANHO_LOTE)

        raw_conn.commit()
        log.info(
            "raw.pagamentos -> trusted.pagamentos concluido: "
            "%d linha(s) carregada(s) (upsert), %d ignorada(s) por transacao nao resolvida",
            len(linhas), sem_transacao,
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na transformacao -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
