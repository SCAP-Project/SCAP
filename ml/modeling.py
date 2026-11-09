"""Treino nao supervisionado e escolha de modelo exclusivamente na validacao."""

import json
import time
import warnings

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import IsolationForest
from sklearn.neural_network import MLPRegressor
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from .config import ARTIFACTS, REPORTS, SEED
from .data import load_labels, sha256
from .evaluation import choose_threshold, compute_metrics
from .features import CATEGORICAL_FEATURES, NUMERIC_FEATURES


def score_bundle(bundle, features):
    if bundle["kind"] == "historical":
        return features.z_historico.where(features.qtd_historico >= 5, 0).to_numpy(dtype=float)
    matrix = bundle["preprocessor"].transform(features)
    if bundle["kind"] == "isolation":
        return -bundle["estimator"].score_samples(matrix)
    reconstructed = bundle["estimator"].predict(matrix)
    return np.mean((matrix - reconstructed) ** 2, axis=1)


def train_models(features, data_dir, artifacts=ARTIFACTS, reports=REPORTS):
    artifacts.mkdir(parents=True, exist_ok=True)
    reports.mkdir(parents=True, exist_ok=True)
    train = features[features.periodo == "treino"].copy()
    validation = features[features.periodo == "validacao"].copy()
    if train.empty or validation.empty:
        raise ValueError("Treino e validacao nao podem ser vazios")
    labels = load_labels(validation.id_transacao_natural, data_dir).flag_anomalia.astype(int).to_numpy()
    preprocessor = ColumnTransformer([
        ("numeric", StandardScaler(), NUMERIC_FEATURES),
        ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), CATEGORICAL_FEATURES),
    ], remainder="drop", sparse_threshold=0)
    matrix = preprocessor.fit_transform(train)
    if not np.isfinite(matrix).all():
        raise ValueError("Matriz de treino invalida")
    joblib.dump(preprocessor, artifacts / "preprocessor.joblib")
    candidates = [
        ("Desvio historico", "historical", None),
        ("Isolation Forest", "isolation", IsolationForest(n_estimators=250, max_samples=512, contamination="auto", random_state=SEED, n_jobs=1)),
        ("Autoencoder", "autoencoder", MLPRegressor(hidden_layer_sizes=(32, 8, 32), activation="relu", solver="adam",
          alpha=0.001, batch_size=256, learning_rate_init=0.001, max_iter=150, early_stopping=False,
          shuffle=True, random_state=SEED, tol=1e-4, n_iter_no_change=15)),
    ]
    rows, all_scores, training_log = [], [], {}
    for name, kind, estimator in candidates:
        print(f"Treinando {name}...", flush=True)
        start = time.perf_counter()
        with warnings.catch_warnings(record=True) as messages, threadpool_limits(limits=1):
            warnings.simplefilter("always")
            if estimator is not None:
                estimator.fit(matrix, matrix) if kind == "autoencoder" else estimator.fit(matrix)
        bundle = dict(name=name, kind=kind, preprocessor=preprocessor, estimator=estimator)
        file = artifacts / f"{kind}.joblib"
        joblib.dump(bundle, file)
        scores = score_bundle(bundle, validation)
        threshold = choose_threshold(labels, scores)
        row = dict(modelo=name, arquivo=file.name, segundos_treino=round(time.perf_counter() - start, 3), **compute_metrics(labels, scores, threshold))
        rows.append(row)
        all_scores.append(pd.DataFrame(dict(id_transacao_natural=validation.id_transacao_natural.to_numpy(), modelo=name, y=labels, score=scores, predicao=scores >= threshold)))
        training_log[name] = dict(kind=kind, parametros=None if estimator is None else estimator.get_params(), avisos=[str(m.message) for m in messages], sha256=sha256(file))
        if kind == "autoencoder":
            pd.DataFrame({"epoca": range(1, len(estimator.loss_curve_) + 1), "loss_treino": estimator.loss_curve_}).to_csv(reports / "autoencoder_loss.csv", index=False)
    metrics = pd.DataFrame(rows).sort_values(["average_precision", "f1", "modelo"], ascending=[False, False, True]).reset_index(drop=True)
    metrics.to_csv(reports / "metricas_validacao.csv", index=False)
    pd.concat(all_scores, ignore_index=True).to_csv(reports / "scores_validacao.csv", index=False)
    selection = {
        "selecionado": metrics.iloc[0].modelo, "criterio": "Maior Average Precision na validacao; desempate por F1 e nome",
        "seed": SEED, "sklearn": sklearn.__version__, "n_treino": len(train), "dimensoes_matriz": matrix.shape[1],
        "preprocessamento": "fit apenas em treino; StandardScaler numerico + OneHotEncoder categorico",
        "treino": "Nao supervisionado; inclui anomalias desconhecidas; nenhum rotulo usado em fit",
        "limiares": "F1 maximo na validacao; empate favorece maior limiar; predicao score >= limiar",
        "modelos": training_log, "features_sha256": sha256(artifacts / "features.csv"),
        "gabarito_sha256": sha256(data_dir / "ground_truth/transacoes_gabarito.csv"),
    }
    (reports / "selecao_validacao.json").write_text(json.dumps(selection, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metrics
