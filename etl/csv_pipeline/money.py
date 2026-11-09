"""Valores financeiros em centavos inteiros e Decimal, sem somas em float."""

from decimal import Decimal, InvalidOperation

import pandas as pd


def cents(values: pd.Series) -> pd.Series:
    def convert(value):
        try:
            amount = Decimal(str(value))
            if not amount.is_finite() or amount != amount.quantize(Decimal("0.01")):
                raise ValueError(f"Valor monetario invalido: {value!r}")
            return int(amount * 100)
        except InvalidOperation as exc:
            raise ValueError(f"Valor monetario invalido: {value!r}") from exc
    return values.map(convert).astype("int64")


def amounts(values: pd.Series) -> pd.Series:
    return values.map(lambda value: (Decimal(int(value)) / 100).quantize(Decimal("0.01")))
