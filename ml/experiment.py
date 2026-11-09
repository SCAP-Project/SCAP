"""Etapas reproduziveis: atributos, periodos, treino e teste final."""

import importlib.metadata
import json
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import pandas as pd

from .config import ARTIFACTS, DATA_DIR, REPORTS, SEED, TRAIN_END, VALIDATION_END, TEST_END
from .data import load_labels, load_tables, sha256
from .evaluation import compute_metrics
from .features import build_features, MODEL_FEATURES
from .modeling import score_bundle, train_models
from .split import assign_periods


def prepare_features(data_dir=DATA_DIR):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    REPORTS.mkdir(parents=True, exist_ok=True)
    features = build_features(load_tables(data_dir)["fact_transacoes_financeiras"])
    features.to_csv(ARTIFACTS / "features.csv", index=False, date_format="%Y-%m-%d")
    dictionary = pd.DataFrame([
        dict(atributo=c, entra_no_modelo=c in MODEL_FEATURES,
             grupo="historico anterior ao dia" if any(s in c for s in ["historico", "90d", "ultima"]) else "transacao/calendario/diagnostico")
        for c in features.columns
    ])
    dictionary.to_csv(REPORTS / "dicionario_atributos.csv", index=False)
    return features


def prepare_split():
    frame = pd.read_csv(ARTIFACTS / "features.csv", dtype={"id_transacao_natural": str, "id_parceiro_natural": str, "id_area_natural": str, "id_categoria_natural": str}, parse_dates=["data"])
    frame["periodo"] = assign_periods(frame)
    if set(frame.periodo) != {"treino", "validacao", "teste"}:
        raise ValueError("Os tres periodos devem conter registros")
    summary = frame.groupby("periodo").agg(inicio=("data", "min"), fim=("data", "max"), registros=("data", "size"), parceiros=("id_parceiro_natural", "nunique"), sem_historico=("sem_historico", "sum")).reindex(["treino", "validacao", "teste"])
    summary.to_csv(REPORTS / "periodos.csv")
    frame.to_csv(ARTIFACTS / "features.csv", index=False, date_format="%Y-%m-%d")
    for name, subset in frame.groupby("periodo"):
        subset.to_csv(ARTIFACTS / f"{name}.csv", index=False, date_format="%Y-%m-%d")
    return frame


def read_features():
    return pd.read_csv(ARTIFACTS / "features.csv", dtype={"id_transacao_natural": str, "id_parceiro_natural": str, "id_area_natural": str, "id_categoria_natural": str}, parse_dates=["data"])


def train():
    return train_models(read_features(), DATA_DIR)


def evaluate_test():
    selection = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))
    if sha256(ARTIFACTS / "features.csv") != selection["features_sha256"] or sha256(DATA_DIR / "ground_truth/transacoes_gabarito.csv") != selection["gabarito_sha256"]:
        raise ValueError("Snapshot mudou depois do treino; refaca o experimento")
    test = read_features().query("periodo == 'teste'").reset_index(drop=True)
    labels = load_labels(test.id_transacao_natural)
    y = labels.flag_anomalia.astype(int).to_numpy()
    validation = pd.read_csv(REPORTS / "metricas_validacao.csv")
    rows, predictions = [], []
    for row in validation.itertuples():
        path = ARTIFACTS / row.arquivo
        kind = path.stem
        if sha256(path) != selection["modelos"][row.modelo]["sha256"]:
            raise ValueError(f"Modelo alterado: {row.modelo}")
        scores = score_bundle(joblib.load(path), test)
        rows.append(dict(modelo=row.modelo, selecionado_na_validacao=row.modelo == selection["selecionado"], **compute_metrics(y, scores, row.limiar)))
        output = test[["id_transacao_natural", "data", "id_parceiro_natural", "id_area_natural", "id_categoria_natural", "tipo_transacao", "valor_bruto", "qtd_historico", "sem_historico"]].copy()
        output["modelo"], output["y"], output["score"] = row.modelo, y, scores
        output["predicao"] = scores >= row.limiar
        output["fator_aplicado"] = labels.fator_aplicado.to_numpy()
        output["tipo_anomalia"] = np.where(y == 0, "normal", np.where(output.fator_aplicado > 1, "inflacao", "reducao"))
        predictions.append(output)
    metrics = pd.DataFrame(rows)
    metrics.to_csv(REPORTS / "metricas_teste.csv", index=False)
    results = pd.concat(predictions, ignore_index=True)
    results.to_csv(REPORTS / "predicoes_teste.csv", index=False, date_format="%Y-%m-%d")
    winner = results[results.modelo == selection["selecionado"]].copy()
    threshold = float(validation.set_index("modelo").loc[selection["selecionado"], "limiar"])
    # Incerteza condicional ao modelo/limiar, reamostrando semanas inteiras.
    weeks = [g.index.to_numpy() for _, g in winner.groupby(winner.data.dt.to_period("W"))]
    rng = np.random.RandomState(SEED)
    bootstrap = []
    for _ in range(200):
        sampled = winner.loc[np.concatenate([weeks[i] for i in rng.randint(0, len(weeks), len(weeks))])]
        bootstrap.append(compute_metrics(sampled.y, sampled.score, threshold))
    intervals = pd.DataFrame(bootstrap)[["average_precision", "f1", "precision", "recall"]].quantile([0.025, 0.975]).T
    intervals.columns = ["limite_inferior_95", "limite_superior_95"]
    intervals.to_csv(REPORTS / "intervalos_bootstrap_semanal.csv")
    manifest = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(), "seed": SEED,
        "periodos": dict(treino_ate=TRAIN_END, validacao_ate=VALIDATION_END, teste_ate=TEST_END),
        "modelo_selecionado_antes_do_teste": selection["selecionado"],
        "protocolo": "Scoring online com historico de dias anteriores; pesos e preprocessor congelados; limiares da validacao",
        "features": MODEL_FEATURES, "features_sha256": sha256(ARTIFACTS / "features.csv"),
        "gabarito_sha256": sha256(DATA_DIR / "ground_truth/transacoes_gabarito.csv"),
        "refined_sha256": {p.name: sha256(p) for p in sorted((DATA_DIR / "refined").glob("*.csv"))},
        "codigo_sha256": {p.name: sha256(p) for p in sorted((ARTIFACTS.parent).glob("*.py"))},
        "python": sys.version,
        "versoes": {p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scikit-learn", "scipy", "matplotlib", "joblib"]},
        "inferencia": "Anomalias sinteticas de valor; nao valida fraude ou risco de credito real",
    }
    (REPORTS / "experimento.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return metrics
