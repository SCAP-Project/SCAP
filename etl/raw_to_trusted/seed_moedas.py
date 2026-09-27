"""Seed de dados de referencia: trusted.moedas (BRL, USD, EUR).

Nao existe raw.moedas -- o escopo do dataset e 100% operacao nacional (toda
transacao em raw.transacoes_financeiras.moeda = 'BRL', ver
dados_transacoes_financeiras.ipynb). trusted.moedas e populada com as 3
moedas de referencia por extensibilidade (documentado no COMMENT ON TABLE),
nao porque existam transacoes em USD/EUR hoje.

Diferente dos transform_*.py, este script nao versiona (SCD2 nao se aplica a
um seed estatico): insere as moedas que ainda nao existem e ignora as que ja
existem (ON CONFLICT DO NOTHING por codigo_iso). Idempotente.

Pre-requisito: sql/ddl/02_create_trusted_tables.sql aplicado.

Uso:
    python -m etl.raw_to_trusted.seed_moedas
"""

from __future__ import annotations

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

SOURCE_SYSTEM = "SEED_MANUAL"

MOEDAS = [
    {"codigo_iso": "BRL", "nome_moeda": "Real Brasileiro", "simbolo": "R$", "pais_referencia": "Brasil"},
    {"codigo_iso": "USD", "nome_moeda": "Dolar Americano", "simbolo": "US$", "pais_referencia": "Estados Unidos"},
    {"codigo_iso": "EUR", "nome_moeda": "Euro", "simbolo": "€", "pais_referencia": "Zona do Euro"},
]

SQL_INSERIR = """
    INSERT INTO trusted.moedas (codigo_iso, nome_moeda, simbolo, pais_referencia, source_system)
    VALUES (:codigo_iso, :nome_moeda, :simbolo, :pais_referencia, :source_system)
    ON CONFLICT (codigo_iso) DO NOTHING
"""


def main() -> None:
    inseridas = 0
    with get_connection() as conn:
        for moeda in MOEDAS:
            resultado = conn.execute(text(SQL_INSERIR), {**moeda, "source_system": SOURCE_SYSTEM})
            inseridas += resultado.rowcount

    log.info(
        "trusted.moedas: %d nova(s) de %d moeda(s) de referencia (%d ja existiam)",
        inseridas, len(MOEDAS), len(MOEDAS) - inseridas,
    )


if __name__ == "__main__":
    main()
