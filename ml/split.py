"""Periodos fixos e contiguos; nenhuma amostragem aleatoria das linhas."""

import numpy as np
import pandas as pd

from .config import TRAIN_END, VALIDATION_END, TEST_END


def assign_periods(frame):
    dates = pd.to_datetime(frame.data)
    if dates.isna().any() or (dates < "2024-01-01").any() or (dates > TEST_END).any():
        raise ValueError("Data fora dos periodos definidos: 2024-01-01 a 2025-12-31")
    return pd.Series(np.select([dates <= TRAIN_END, dates <= VALIDATION_END], ["treino", "validacao"], default="teste"), index=frame.index, name="periodo")
