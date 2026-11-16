"""Carrega data/raw/<entidade> em raw.<entidade> por COPY FROM STDIN.

Mapeia as colunas pelo cabeçalho do CSV. --no-truncate evita a limpeza inicial."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path

from etl.config import get_engine, get_logger, settings

log = get_logger(__name__)

# Dimensões precedem as transações na carga RAW.
ENTIDADES = [
    "areas",
    "categorias_contabeis",
    "fornecedores_clientes",
    "funcionarios",
    "transacoes_financeiras",
    "pagamentos",
    "recebimentos",
]


def _csv_files(entidade: str) -> list[Path]:
    """Retorna os CSVs de uma entidade (a pasta pode ter varios, ex.: mensais)."""
    pasta = settings.data_raw_dir / entidade
    if not pasta.is_dir():
        log.warning("Pasta inexistente: %s -- entidade '%s' ignorada", pasta, entidade)
        return []
    arquivos = sorted(pasta.glob("*.csv"))
    if not arquivos:
        log.warning("Nenhum CSV em %s -- entidade '%s' ignorada", pasta, entidade)
    return arquivos


def _colunas(arquivo: Path) -> list[str]:
    """Le o cabecalho do CSV para montar a lista de colunas do COPY."""
    with arquivo.open("r", encoding="utf-8", newline="") as f:
        return next(csv.reader(f))


def carregar_entidade(raw_conn, entidade: str, truncate: bool) -> int:
    """Carrega todos os CSVs de uma entidade em raw.<entidade>. Retorna linhas inseridas."""
    tabela = f"raw.{entidade}"
    arquivos = _csv_files(entidade)
    if not arquivos:
        return 0

    total = 0
    with raw_conn.cursor() as cur:
        if truncate:
            log.info("TRUNCATE %s", tabela)
            cur.execute(f"TRUNCATE TABLE {tabela};")

        for arquivo in arquivos:
            colunas = ", ".join(f'"{c}"' for c in _colunas(arquivo))
            copy_sql = (
                f"COPY {tabela} ({colunas}) FROM STDIN WITH (FORMAT csv, HEADER true)"
            )
            with arquivo.open("r", encoding="utf-8") as f:
                cur.copy_expert(copy_sql, f)
            log.info("  %-28s -> %s (%d linhas)", arquivo.name, tabela, cur.rowcount)
            total += cur.rowcount

    return total


def main(truncate: bool = True) -> None:
    log.info("Carga RAW iniciada (banco '%s', truncate=%s)", settings.db_name, truncate)
    raw_conn = get_engine().raw_connection()
    try:
        total_geral = sum(
            carregar_entidade(raw_conn, entidade, truncate) for entidade in ENTIDADES
        )
        raw_conn.commit()
        log.info("Carga RAW concluida: %d linhas no total", total_geral)
    except Exception:
        raw_conn.rollback()
        log.exception("Falha na carga RAW -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Carga da camada RAW (CSVs -> RDS PostgreSQL)"
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Nao truncar as tabelas antes de carregar (padrao: trunca para recarga idempotente)",
    )
    args = parser.parse_args()
    main(truncate=not args.no_truncate)
