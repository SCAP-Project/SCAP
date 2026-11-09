"""Atributos disponiveis na transacao; historico estritamente anterior ao dia."""

import numpy as np
import pandas as pd

NUMERIC_FEATURES = [
    "log_valor", "desvio_log_historico", "z_historico", "log_qtd_historico",
    "desvio_log_90d", "z_90d", "log_qtd_90d", "log_dias_desde_ultima",
    "sem_historico", "mes_sin", "mes_cos", "dia_semana_sin", "dia_semana_cos",
]
CATEGORICAL_FEATURES = ["tipo_transacao", "id_area_natural", "id_categoria_natural"]
MODEL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
REQUIRED = ["id_transacao_natural", "data", "id_parceiro_natural", "valor_bruto"] + CATEGORICAL_FEATURES


def build_features(transactions):
    """Janela online: dias anteriores podem atualizar contexto, nunca o modelo.

    Todas as transacoes do mesmo dia usam o mesmo historico. Nao existe ordem
    intradiaria na fonte. Sem historico, desvios sao zero e ha uma flag explicita.
    O piso 0.15 para desvio-padrao log evita dividir por variancia nula.
    """
    frame = transactions[REQUIRED].copy()
    if frame.id_transacao_natural.duplicated().any():
        raise ValueError("Transacao duplicada")
    frame["data"] = pd.to_datetime(frame.data).dt.normalize()
    frame["valor_bruto"] = pd.to_numeric(frame.valor_bruto, errors="raise")
    if frame[REQUIRED].isna().any().any() or (frame.valor_bruto <= 0).any():
        raise ValueError("Campos obrigatorios invalidos nas features")
    frame = frame.sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)
    frame["log_valor"] = np.log1p(frame.valor_bruto)
    frame["log_quadrado"] = frame.log_valor ** 2
    group_keys = ["id_parceiro_natural", "tipo_transacao"]
    daily = frame.groupby(group_keys + ["data"], as_index=False).agg(
        n=("log_valor", "size"), total=("log_valor", "sum"), quadrado=("log_quadrado", "sum"))
    histories = []
    for _, group in daily.groupby(group_keys, sort=True):
        group = group.sort_values("data").copy()
        past = group[["n", "total", "quadrado"]].cumsum() - group[["n", "total", "quadrado"]]
        rolling = group.set_index("data")[["n", "total", "quadrado"]].rolling("90D", closed="left").sum().fillna(0)
        for suffix, stats in [("historico", past.reset_index(drop=True)), ("90d", rolling.reset_index(drop=True))]:
            counts = stats.n.to_numpy()
            denominator = np.maximum(counts, 1)
            mean = stats.total.to_numpy() / denominator
            variance = np.maximum(stats.quadrado.to_numpy() / denominator - mean ** 2, 0)
            group[f"qtd_{suffix}"] = counts
            group[f"media_log_{suffix}"] = np.where(counts > 0, mean, np.nan)
            group[f"std_log_{suffix}"] = np.maximum(np.sqrt(variance), 0.15)
        group["dias_desde_ultima"] = group.data.diff().dt.days.fillna(365).clip(0, 365)
        histories.append(group.drop(columns=["n", "total", "quadrado"]))
    history = pd.concat(histories, ignore_index=True)
    frame = frame.merge(history, on=group_keys + ["data"], validate="many_to_one")
    for suffix in ["historico", "90d"]:
        frame[f"desvio_log_{suffix}"] = (frame.log_valor - frame[f"media_log_{suffix}"]).fillna(0)
        frame[f"z_{suffix}"] = frame[f"desvio_log_{suffix}"].abs() / frame[f"std_log_{suffix}"]
        frame[f"log_qtd_{suffix}"] = np.log1p(frame[f"qtd_{suffix}"])
    frame["log_dias_desde_ultima"] = np.log1p(frame.dias_desde_ultima)
    frame["sem_historico"] = (frame.qtd_historico == 0).astype(int)
    frame["mes_sin"] = np.sin(2 * np.pi * frame.data.dt.month / 12)
    frame["mes_cos"] = np.cos(2 * np.pi * frame.data.dt.month / 12)
    frame["dia_semana_sin"] = np.sin(2 * np.pi * frame.data.dt.dayofweek / 7)
    frame["dia_semana_cos"] = np.cos(2 * np.pi * frame.data.dt.dayofweek / 7)
    if not np.isfinite(frame[NUMERIC_FEATURES].to_numpy()).all():
        raise ValueError("Atributo numerico nao finito")
    return frame.drop(columns="log_quadrado").sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)
