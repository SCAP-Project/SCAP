"""Auditoria por recalculo independente e controles negativos."""

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score

from ml.config import ARTIFACTS, REPORTS
from ml.data import load_tables, load_labels, sha256
from ml.evaluation import compute_metrics
from ml.experiment import read_features
from ml.features import build_features, MODEL_FEATURES, NUMERIC_FEATURES
from ml.modeling import score_bundle


def manual_history_check(source, features, sample_size=100):
    source = source.copy()
    source["data"] = pd.to_datetime(source.data)
    lookup = features.set_index("id_transacao_natural")
    sampled = source.sample(n=min(sample_size, len(source)), random_state=741)
    failures = []
    for row in sampled.itertuples():
        history = source[(source.data < row.data) & (source.id_parceiro_natural == row.id_parceiro_natural) & (source.tipo_transacao == row.tipo_transacao)]
        actual = lookup.loc[row.id_transacao_natural]
        for suffix, data in [("historico", history), ("90d", history[history.data >= row.data - pd.Timedelta(days=90)])]:
            mean = np.log1p(data.valor_bruto.astype(float)).mean() if len(data) else np.nan
            mean_matches = pd.isna(actual[f"media_log_{suffix}"]) if not len(data) else np.isclose(actual[f"media_log_{suffix}"], mean, atol=1e-8, rtol=1e-8)
            if actual[f"qtd_{suffix}"] != len(data) or not mean_matches:
                failures.append(f"{row.id_transacao_natural}: {suffix}")
    return dict(aprovado=not failures, amostra=len(sampled), falhas=failures[:20], metodo="Filtros diretos por parceiro/tipo e data < atual; media log calculada sem reutilizar build_features")


def run_audit(destination):
    source = load_tables()["fact_transacoes_financeiras"]
    features = read_features()
    checks = []
    def record(name, ok, details):
        checks.append(dict(verificacao=name, aprovado=bool(ok), detalhes=details))
    manual = manual_history_check(source, features, 150)
    record("Historicos recalculados de forma independente", manual["aprovado"], manual)
    forbidden = {"flag_anomalia", "fator_aplicado", "valor_original", "perfil_risco", "flag_ajuste", "flag_alto_valor",
                 "valor_liquido", "status_pagamento", "rating_credito", "prazo_medio", "parceiro_sk", "transacao_sk"}
    record("Whitelist de atributos", not forbidden.intersection(MODEL_FEATURES), {"matriz": MODEL_FEATURES, "intersecao_proibida": sorted(forbidden.intersection(MODEL_FEATURES))})
    altered = source.copy()
    altered.loc[altered.data >= "2025-01-01", "valor_bruto"] *= 20
    for column in forbidden:
        altered[column] = "VALOR_ADULTERADO"
    rebuilt = build_features(altered).set_index("id_transacao_natural")
    original = features[features.data < "2025-01-01"].set_index("id_transacao_natural")
    same = np.allclose(original[NUMERIC_FEATURES], rebuilt.loc[original.index, NUMERIC_FEATURES], atol=1e-9)
    record("Mutar futuro e colunas proibidas preserva passado", same, {"linhas_passadas": len(original), "mutacao_valor_futuro": "x20"})
    train, validation, test = [features[features.periodo == name] for name in ["treino", "validacao", "teste"]]
    ids = [set(frame.id_transacao_natural) for frame in [train, validation, test]]
    record("Periodos e identificadores disjuntos", not (ids[0] & ids[1] or ids[1] & ids[2] or ids[0] & ids[2]) and train.data.max() < validation.data.min() and validation.data.max() < test.data.min(), {"registros": [len(train), len(validation), len(test)]})
    keys = ["id_parceiro_natural", "tipo_transacao", "id_area_natural", "id_categoria_natural", "valor_bruto"]
    shared = pd.util.hash_pandas_object(train[keys], index=False).isin(pd.util.hash_pandas_object(test[keys], index=False))
    record("Sem copia exata de negocios entre treino e teste", not shared.any(), {"assinaturas_compartilhadas": int(shared.sum()), "nota": "Mesmo parceiro em periodos diferentes e esperado; nao avalia cold-start puro"})
    bundle = joblib.load(ARTIFACTS / "isolation.joblib")
    scaler = bundle["preprocessor"].named_transformers_["numeric"]
    matches = int(scaler.n_samples_seen_) == len(train) and np.allclose(scaler.mean_, train[NUMERIC_FEATURES].mean().to_numpy(), atol=1e-8)
    record("Scaler compativel com ajuste apenas no treino", matches, {"n_samples_seen": int(scaler.n_samples_seen_), "treino": len(train)})
    selection = json.loads((REPORTS / "selecao_validacao.json").read_text(encoding="utf-8"))
    y = load_labels(test.id_transacao_natural).flag_anomalia.astype(int).to_numpy()
    metrics = pd.read_csv(REPORTS / "metricas_teste.csv").set_index("modelo")
    validation_metrics = pd.read_csv(REPORTS / "metricas_validacao.csv")
    recomputed = []
    baseline_scores = None
    for row in validation_metrics.itertuples():
        model_path = ARTIFACTS / row.arquivo
        consistent_hash = sha256(model_path) == selection["modelos"][row.modelo]["sha256"]
        scores = score_bundle(joblib.load(model_path), test)
        recomputed_metrics = compute_metrics(y, scores, row.limiar)
        matches = all(np.isclose(value, metrics.loc[row.modelo, name], atol=1e-10) for name, value in recomputed_metrics.items())
        recomputed.append(dict(modelo=row.modelo, hash_confere=consistent_hash, metricas_conferem=matches))
        if row.modelo == selection["selecionado"]:
            baseline_scores = scores
    record("Scores e metricas originais reproduzidos", all(row["hash_confere"] and row["metricas_conferem"] for row in recomputed), recomputed)
    rng = np.random.RandomState(8101)
    null = pd.DataFrame({"permutacao": range(100), "average_precision": [average_precision_score(rng.permutation(y), baseline_scores) for _ in range(100)]})
    null.to_csv(destination / "controle_negativo.csv", index=False)
    negative = dict(ap_observada=float(average_precision_score(y, baseline_scores)), ap_permutada_media=float(null.average_precision.mean()),
                    ap_permutada_min=float(null.average_precision.min()), ap_permutada_max=float(null.average_precision.max()), prevalencia=float(y.mean()),
                    nota="Controle negativo de associacao; nao prova realismo nem generalizacao e nao e teste causal")
    report = dict(verificacoes=checks, controle_negativo=negative, todos_aprovados=all(row["aprovado"] for row in checks))
    (destination / "auditoria.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
