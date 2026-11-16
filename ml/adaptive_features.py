"""Contexto recente por parceiro/tipo, com exclusão de todo o dia atual."""
import numpy as np
import pandas as pd

from .features import REQUIRED

ADAPTIVE_FEATURES = [
    "desvio_20d",
    "z_20d",
    "std_20d",
    "log_n_20d",
    "desvio_60d",
    "z_60d",
    "std_60d",
    "log_n_60d",
    "mudanca_mediana",
    "log_intervalo",
]


def build_adaptive_features(transactions):
    frame = transactions[REQUIRED].copy()
    frame["data"] = pd.to_datetime(frame.data).dt.normalize()
    if frame.id_transacao_natural.duplicated().any() or frame.isna().any().any():
        raise ValueError("Transações duplicadas ou campos ausentes")
    if not np.isfinite(frame.valor_bruto).all() or (frame.valor_bruto <= 0).any():
        raise ValueError("Valores devem ser positivos e finitos")
    frame = frame.sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)
    rows = []
    for _, group in frame.groupby(["id_parceiro_natural", "tipo_transacao"], sort=True):
        dates = []
        values = []
        last = None
        for day, batch in group.groupby("data", sort=True):
            past_dates = np.asarray(dates, dtype="datetime64[ns]")
            past_values = np.asarray(values, dtype=float)
            stats = {}
            for window in [20, 60]:
                start = np.datetime64(day - pd.Timedelta(days=window))
                history = past_values[past_dates >= start]
                median = float(np.median(history)) if len(history) else 0.0
                mad = (
                    float(np.median(np.abs(history - median))) if len(history) else 0.0
                )
                stats[window] = (len(history), median, max(1.4826 * mad, 0.10))
            for row in batch.itertuples():
                current = np.log1p(row.valor_bruto)
                output = {"id_transacao_natural": row.id_transacao_natural}
                for window, (n, median, scale) in stats.items():
                    deviation = current - median if n else 0.0
                    output.update(
                        {
                            f"n_{window}d": n,
                            f"desvio_{window}d": deviation,
                            f"z_{window}d": abs(deviation) / scale,
                            f"std_{window}d": scale,
                            f"log_n_{window}d": np.log1p(n),
                        }
                    )
                output["mudanca_mediana"] = (
                    stats[20][1] - stats[60][1]
                    if stats[20][0] and stats[60][0]
                    else 0.0
                )
                output["log_intervalo"] = np.log1p(
                    min((day - last).days, 365) if last is not None else 365
                )
                rows.append(output)
            # Somente após pontuar o dia inteiro é permitido incorporá-lo ao contexto.
            dates.extend([day] * len(batch))
            values.extend(np.log1p(batch.valor_bruto).tolist())
            last = day
    result = frame.merge(
        pd.DataFrame(rows), on="id_transacao_natural", validate="one_to_one"
    )
    assert np.isfinite(result[ADAPTIVE_FEATURES]).all().all()
    return result
