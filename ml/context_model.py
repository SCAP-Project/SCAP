"""Atributos explícitos e inferência sem gabarito para a extensão documental."""
import numpy as np
import pandas as pd

from .adaptive_features import ADAPTIVE_FEATURES, build_adaptive_features
from .features import REQUIRED, build_features
from .context_data import INPUT_COLUMNS, validate_context_input

HISTORY_FEATURES = ADAPTIVE_FEATURES + ["log_valor", "z_historico", "log_qtd_historico"]
DOCUMENT_FEATURES = [
    "log_razao_documento",
    "abs_log_razao_documento",
    "sem_documento",
    "idade_documento",
]
CONTEXT_FEATURES = HISTORY_FEATURES + DOCUMENT_FEATURES


def build_context_features(source):
    source = validate_context_input(source)
    adaptive = build_adaptive_features(source[REQUIRED]).set_index(
        "id_transacao_natural"
    )
    base = build_features(source[REQUIRED]).set_index("id_transacao_natural")
    result = source.set_index("id_transacao_natural").loc[adaptive.index].copy()
    for name in ADAPTIVE_FEATURES + ["n_60d"]:
        result[name] = adaptive[name]
    for name in ["log_valor", "z_historico", "log_qtd_historico", "qtd_historico"]:
        result[name] = base[name]
    present = result.id_documento.notna()
    reference = result.quantidade_documento * result.preco_unitario_documento
    result["log_razao_documento"] = np.where(
        present, np.log1p(result.valor_bruto) - np.log1p(reference), 0.0
    )
    result["abs_log_razao_documento"] = result.log_razao_documento.abs()
    result["sem_documento"] = (~present).astype(int)
    result["idade_documento"] = (
        (result.data - result.data_documento).dt.days.fillna(0).astype(float)
    )
    if not np.isfinite(result[CONTEXT_FEATURES]).all().all():
        raise ValueError("Atributo não finito")
    return result.reset_index()


def score_candidate(bundle, features):
    kind = bundle["kind"]
    if kind == "historical":
        return features.z_historico.where(features.qtd_historico >= 5, 0).to_numpy()
    if kind == "median":
        return features.z_60d.where(features.n_60d >= 5, 0).to_numpy()
    if kind == "document_rule":
        return features.abs_log_razao_documento.to_numpy()
    return bundle["estimator"].predict_proba(features[bundle["features"]])[:, 1]


def predict_context(history, batch, bundle, threshold):
    history = validate_context_input(history)
    batch = validate_context_input(batch)
    if history.data.max() >= batch.data.min():
        raise ValueError("Histórico deve ser anterior ao lote")
    if set(history.id_transacao_natural) & set(batch.id_transacao_natural):
        raise ValueError("IDs sobrepostos")
    features = build_context_features(pd.concat([history, batch], ignore_index=True))
    features = features[
        features.id_transacao_natural.isin(batch.id_transacao_natural)
    ].copy()
    scores = score_candidate(bundle, features)
    result = features[INPUT_COLUMNS].copy()
    result["score"] = scores
    result["limiar"] = threshold
    result["alerta"] = scores >= threshold
    result["documento_disponivel"] = features.sem_documento.eq(0)
    result["contexto_historico_suficiente"] = features.n_60d.ge(5)
    return result.sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)
