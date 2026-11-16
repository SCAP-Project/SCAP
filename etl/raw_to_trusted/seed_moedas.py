"""Insere BRL, USD e EUR em trusted.moedas, sem substituir registros existentes.

O gerador atual usa BRL; as demais moedas são referências para expansão."""

from __future__ import annotations

from sqlalchemy import text

from etl.config import get_connection, get_logger

log = get_logger(__name__)

SOURCE_SYSTEM = "SEED_MANUAL"

MOEDAS = [
    {
        "codigo_iso": "BRL",
        "nome_moeda": "Real Brasileiro",
        "simbolo": "R$",
        "pais_referencia": "Brasil",
    },
    {
        "codigo_iso": "USD",
        "nome_moeda": "Dolar Americano",
        "simbolo": "US$",
        "pais_referencia": "Estados Unidos",
    },
    {
        "codigo_iso": "EUR",
        "nome_moeda": "Euro",
        "simbolo": "€",
        "pais_referencia": "Zona do Euro",
    },
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
            resultado = conn.execute(
                text(SQL_INSERIR), {**moeda, "source_system": SOURCE_SYSTEM}
            )
            inseridas += resultado.rowcount

    log.info(
        "trusted.moedas: %d nova(s) de %d moeda(s) de referencia (%d ja existiam)",
        inseridas,
        len(MOEDAS),
        len(MOEDAS) - inseridas,
    )


if __name__ == "__main__":
    main()
