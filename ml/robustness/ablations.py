"""Diagnostico por retirada de atributos; nenhuma escolha baseada no teste."""

import json
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from ml.config import ARTIFACTS, DATA_DIR
from ml.data import load_labels
from ml.evaluation import choose_threshold, compute_metrics
from ml.experiment import read_features
from ml.features import CATEGORICAL_FEATURES, NUMERIC_FEATURES
from ml.modeling import score_bundle

CALENDAR = ["mes_sin", "mes_cos", "dia_semana_sin", "dia_semana_cos"]
CURRENT_VALUE = ["log_valor", "desvio_log_historico", "z_historico", "desvio_log_90d", "z_90d"]
HISTORY = [c for c in NUMERIC_FEATURES if c not in ["log_valor"] + CALENDAR]
FEATURE_GROUPS = {
    "completo": (NUMERIC_FEATURES, CATEGORICAL_FEATURES),
    "sem_historico": (["log_valor"] + CALENDAR, CATEGORICAL_FEATURES),
    "so_historico": (HISTORY, []),
    "sem_categorias": (NUMERIC_FEATURES, []),
    "sem_calendario": ([c for c in NUMERIC_FEATURES if c not in CALENDAR], CATEGORICAL_FEATURES),
    "sem_valor_atual": ([c for c in NUMERIC_FEATURES if c not in CURRENT_VALUE], CATEGORICAL_FEATURES),
}
GROUP_LABELS = {
    "completo": "Completo", "sem_historico": "Sem histórico",
    "so_historico": "Desvios atuais + histórico", "sem_categorias": "Sem categorias",
    "sem_calendario": "Sem calendário", "sem_valor_atual": "Sem valor atual e derivados",
}
# A chave interna so_historico foi mantida para rastrear o protocolo inicial.
# Seu grupo inclui desvios da transacao atual em relacao ao passado, nao
# apenas informacoes passadas. sem_valor_atual e o controle sem esses desvios.


def run_ablations(destination, model_dir):
    frame = read_features()
    train, validation, test = [frame[frame.periodo == name].copy() for name in ["treino", "validacao", "teste"]]
    yv = load_labels(validation.id_transacao_natural).flag_anomalia.astype(int).to_numpy()
    yt = load_labels(test.id_transacao_natural).flag_anomalia.astype(int).to_numpy()
    model_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for group, (numeric, categorical) in FEATURE_GROUPS.items():
        transforms = [("numeric", StandardScaler(), numeric)]
        if categorical:
            transforms.append(("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), categorical))
        processor = ColumnTransformer(transforms, remainder="drop", sparse_threshold=0)
        matrix = processor.fit_transform(train)
        for kind in ["isolation", "autoencoder"]:
            print(f"Ablacao {group} / {kind}...", flush=True)
            original = joblib.load(ARTIFACTS / f"{kind}.joblib")
            estimator = clone(original["estimator"])
            with warnings.catch_warnings(record=True) as messages, threadpool_limits(limits=1):
                warnings.simplefilter("always")
                estimator.fit(matrix, matrix) if kind == "autoencoder" else estimator.fit(matrix)
            bundle = dict(kind=kind, estimator=estimator, preprocessor=processor)
            joblib.dump(bundle, model_dir / f"{group}_{kind}.joblib")
            scores_v = score_bundle(bundle, validation)
            threshold = choose_threshold(yv, scores_v)
            mv = compute_metrics(yv, scores_v, threshold)
            mt = compute_metrics(yt, score_bundle(bundle, test), threshold)
            rows.append(dict(grupo=group, modelo=original["name"], n_atributos=len(numeric) + len(categorical),
                             dimensoes=matrix.shape[1], ap_validacao=mv["average_precision"], f1_validacao=mv["f1"],
                             avisos=" | ".join(str(w.message) for w in messages), **mt))
    # Referencias transparentes: global sem parceiro versus historico e 90 dias.
    for name, sv, st in [
        ("Historico completo", validation.z_historico.where(validation.qtd_historico >= 5, 0), test.z_historico.where(test.qtd_historico >= 5, 0)),
        ("Historico 90 dias", validation.z_90d.where(validation.qtd_90d >= 5, 0), test.z_90d.where(test.qtd_90d >= 5, 0)),
        ("Valor global", (validation.log_valor - train.log_valor.mean()).abs() / train.log_valor.std(ddof=0), (test.log_valor - train.log_valor.mean()).abs() / train.log_valor.std(ddof=0)),
    ]:
        threshold = choose_threshold(yv, sv)
        mv = compute_metrics(yv, sv, threshold)
        rows.append(dict(grupo=name, modelo="Regra", n_atributos=1, dimensoes=1,
                         ap_validacao=mv["average_precision"], f1_validacao=mv["f1"], avisos="", **compute_metrics(yt, st, threshold)))
    result = pd.DataFrame(rows)
    result.to_csv(destination / "ablacoes.csv", index=False)
    (destination / "grupos_atributos.json").write_text(json.dumps(FEATURE_GROUPS, indent=2, ensure_ascii=False), encoding="utf-8")
    return result
