"""Carga do gabarito de anomalias: CSV local -> ml.transacoes_gabarito.

O gabarito e o ground truth do experimento controlado: quais transacoes tiveram
o valor deliberadamente distorcido pelo gerador de dados sinteticos. Ele NAO
vive no Medallion de proposito -- um ERP real nao sabe dizer o que e anomalia, e
manter o rotulo fora de raw/trusted/refined evita vazamento de rotulo (target
leakage) no pipeline. A juncao com os dados e feita por id_transacao_raw APENAS
na etapa de avaliacao do modelo.

Origem: data/ground_truth/transacoes_gabarito.csv, produzido por
etl/data_generation/generators/dados_transacoes_financeiras.ipynb

Pre-requisito: sql/ddl/05_create_ml_tables.sql aplicado (roda como scap_admin).

Uso:
    python -m etl.load_ml.load_gabarito                # trunca e recarrega
    python -m etl.load_ml.load_gabarito --no-truncate  # apenas anexa
"""

from __future__ import annotations

import argparse
import csv

from etl.config import get_engine, get_logger, settings

log = get_logger(__name__)

TABELA = "ml.transacoes_gabarito"


def _caminho_csv():
    return settings.data_raw_dir.parent / "ground_truth" / "transacoes_gabarito.csv"


def main(truncate: bool = True) -> None:
    arquivo = _caminho_csv()
    if not arquivo.is_file():
        raise FileNotFoundError(
            f"Gabarito nao encontrado em {arquivo}. "
            f"Rode o notebook dados_transacoes_financeiras.ipynb para gera-lo."
        )

    log.info("Carga do gabarito iniciada (banco '%s', truncate=%s)", settings.db_name, truncate)

    with arquivo.open("r", encoding="utf-8", newline="") as f:
        colunas = next(csv.reader(f))
    lista_colunas = ", ".join(f'"{c}"' for c in colunas)

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            if truncate:
                log.info("TRUNCATE %s", TABELA)
                cur.execute(f"TRUNCATE TABLE {TABELA};")

            copy_sql = (
                f"COPY {TABELA} ({lista_colunas}) FROM STDIN WITH (FORMAT csv, HEADER true)"
            )
            with arquivo.open("r", encoding="utf-8") as f:
                cur.copy_expert(copy_sql, f)
            total = cur.rowcount
            log.info("  %-32s -> %s (%d linhas)", arquivo.name, TABELA, total)

            cur.execute(f"SELECT count(*) FILTER (WHERE flag_anomalia), count(*) FROM {TABELA};")
            anomalas, geral = cur.fetchone()

        raw_conn.commit()
        log.info(
            "Carga concluida: %d linhas, %d anomalias (%.2f%%)",
            geral, anomalas, 100 * anomalas / geral if geral else 0,
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na carga do gabarito -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Carga do gabarito de anomalias (CSV -> schema ml)")
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Nao truncar a tabela antes de carregar (padrao: trunca para recarga idempotente)",
    )
    args = parser.parse_args()
    main(truncate=not args.no_truncate)
