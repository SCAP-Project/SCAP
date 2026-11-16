"""Compara novos candidatos sem substituir os experimentos anteriores."""
from datetime import datetime, timezone
from pathlib import Path
import importlib.metadata
import json

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import precision_recall_curve
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .adaptive_features import ADAPTIVE_FEATURES, build_adaptive_features
from .client_demo import (
    CONFIG,
    DATASET,
    generate_client_data,
    read_input,
    selected_model,
)
from .config import ROOT, REPORTS, ARTIFACTS
from .data import load_tables, sha256
from .evaluation import compute_metrics
from .features import build_features
from .modeling import score_bundle

DEST = REPORTS / "melhoria/rodada_02"
STORE = ARTIFACTS / "melhoria/rodada_02"
DEV_SEEDS = [81001, 81002, 81003]
TEST_SEEDS = [91001, 91002, 91003, 91004, 91005]
MIN_RECALL = 0.35
BETA = 0.5
CANDIDATES = [
    "Original congelado",
    "Historico recalibrado",
    "Mediana 20 dias",
    "Mediana 60 dias",
    "Isolation Forest contextual",
]


def calibrate(y, scores, min_recall=MIN_RECALL):
    """F0,5 máximo, recall >= piso e pelo menos dez alertas na validação."""
    y = np.asarray(y, dtype=int)
    scores = np.asarray(scores, dtype=float)
    if set(np.unique(y)) != {0, 1} or not np.isfinite(scores).all():
        raise ValueError("Validação inválida")
    precision, recall, thresholds = precision_recall_curve(y, scores)
    counts = np.array([(scores >= t).sum() for t in thresholds])
    valid = (recall[:-1] >= min_recall) & (counts >= 10) & (thresholds > 0)
    if not valid.any():
        raise ValueError("Nenhum limiar atende aos critérios")
    objective = (
        (1 + BETA**2)
        * precision[:-1]
        * recall[:-1]
        / np.maximum(BETA**2 * precision[:-1] + recall[:-1], 1e-12)
    )
    objective[~valid] = -np.inf
    best = np.flatnonzero(np.isclose(objective, objective.max(), rtol=0, atol=1e-12))[
        -1
    ]
    return float(thresholds[best])


def fbeta(metrics):
    p, r = metrics["precision"], metrics["recall"]
    return (1 + BETA**2) * p * r / max(BETA**2 * p + r, 1e-12)


def freeze():
    DEST.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)
    originals = json.loads(
        (REPORTS / "cliente_dummy/rodada_01/protocolo.json").read_text(encoding="utf-8")
    )["originais_sha256"]
    for name, digest in originals.items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Original modificado: " + name)
    files = [
        Path(__file__),
        ROOT / "ml/adaptive_features.py",
        ROOT / "ml/client_demo.py",
        ROOT / "ml/features.py",
        ROOT / "ml/modeling.py",
        ROOT / "ml/evaluation.py",
    ]
    settings = dict(
        seeds_desenvolvimento=DEV_SEEDS,
        seeds_teste=TEST_SEEDS,
        configuracao_cliente=CONFIG,
        candidatos=CANDIDATES,
        min_recall_validacao=MIN_RECALL,
        beta=BETA,
        treino="Históricos sem rótulos, janeiro–março de 2026, três clientes de desenvolvimento",
        validacao="Abril de 2026, três clientes de desenvolvimento; rótulos somente para seleção e limiar",
        teste="Maio de 2026, cinco novos clientes; históricos janeiro–abril; sem reajuste após seleção",
        limite="Novo teste independente da seleção, mas da mesma família de gerador sintético já conhecida",
        escala_robusta="1.4826 * MAD; piso 0.10; janelas de 20 e 60 dias corridos; mínimo 5 observações",
        isolation=dict(n_estimators=250, max_samples=512, random_state=42, n_jobs=1),
        criterio="Maior F0.5 na validação com recall>=0.35; desempates AP, precisão e nome",
        regra_comparacao="Reportar todos; melhoria exige precisão e F1 maiores que original e perda de recall <=0.10 no teste agregado",
        regras="Sem seleção de sementes ou inspeção de métricas do teste antes de congelar o selecionado",
    )
    payload = dict(
        configuracao=settings,
        originais_sha256=originals,
        metodos_sha256={str(p.relative_to(ROOT)): sha256(p) for p in files},
        versoes={
            p: importlib.metadata.version(p)
            for p in ["numpy", "pandas", "scikit-learn", "scipy", "joblib"]
        },
    )
    path = DEST / "protocolo.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous[k] != v for k, v in payload.items()):
            raise ValueError(
                "Protocolo alterado; preserve a rodada e crie outra explicitamente"
            )
        return previous
    payload["registrado_em_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def prepare(context, seed, stage):
    config = dict(CONFIG, seed=seed)
    if stage == "teste":
        config.update(
            historico_fim="2026-04-30", lote_inicio="2026-05-01", lote_fim="2026-05-31"
        )
    history, batch, labels = generate_client_data(context, config)
    folder = STORE / stage / f"seed_{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    for name, frame in [("historico", history), ("lote", batch), ("gabarito", labels)]:
        frame.to_csv(
            folder / (name + ".csv"),
            index=False,
            date_format="%Y-%m-%d",
            lineterminator="\n",
        )
    history = read_input(folder / "historico.csv")
    batch = read_input(folder / "lote.csv")
    joined = pd.concat([history, batch], ignore_index=True)
    base = build_features(joined).set_index("id_transacao_natural")
    adaptive = build_adaptive_features(joined).set_index("id_transacao_natural")
    train = adaptive.loc[history.id_transacao_natural].copy()
    evaluate = adaptive.loc[batch.id_transacao_natural].copy()
    base_batch = base.loc[batch.id_transacao_natural].copy()
    y = (
        labels.set_index("id_transacao_natural")
        .loc[batch.id_transacao_natural, "flag_anomalia"]
        .astype(int)
        .to_numpy()
    )
    return train, evaluate, base_batch, y, labels


def scores_for(name, adaptive, base, original_bundle, scaler, estimator):
    if name in CANDIDATES[:2]:
        return score_bundle(original_bundle, base)
    if name.startswith("Mediana"):
        window = 20 if name == "Mediana 20 dias" else 60
        return (
            adaptive[f"z_{window}d"].where(adaptive[f"n_{window}d"] >= 5, 0).to_numpy()
        )
    return np.where(
        adaptive.n_60d >= 5,
        -estimator.score_samples(scaler.transform(adaptive[ADAPTIVE_FEATURES])),
        0,
    )


def run():
    protocol = freeze()
    print("Protocolo registrado. Preparando somente desenvolvimento...", flush=True)
    context = load_tables()["fact_transacoes_financeiras"]
    _, model_path, original_threshold = selected_model()
    original_bundle = joblib.load(model_path)
    dev = [prepare(context, seed, "desenvolvimento") for seed in DEV_SEEDS]
    training = pd.concat([r[0] for r in dev])
    training = training[training.n_60d >= 5]
    scaler = StandardScaler().fit(training[ADAPTIVE_FEATURES])
    estimator = IsolationForest(**protocol["configuracao"]["isolation"])
    with threadpool_limits(limits=1):
        estimator.fit(scaler.transform(training[ADAPTIVE_FEATURES]))
    joblib.dump(
        dict(scaler=scaler, estimator=estimator, features=ADAPTIVE_FEATURES),
        STORE / "isolation_contextual.joblib",
    )
    ydev = np.concatenate([r[3] for r in dev])
    rows = []
    thresholds = {}
    dev_predictions = []
    for name in CANDIDATES:
        scores = np.concatenate(
            [
                scores_for(name, r[1], r[2], original_bundle, scaler, estimator)
                for r in dev
            ]
        )
        threshold = (
            original_threshold
            if name == "Original congelado"
            else calibrate(ydev, scores)
        )
        thresholds[name] = threshold
        metrics = compute_metrics(ydev, scores, threshold)
        metrics["f0_5"] = fbeta(metrics)
        rows.append(dict(modelo=name, **metrics))
        dev_predictions.append(pd.DataFrame(dict(modelo=name, y=ydev, score=scores)))
    validation = pd.DataFrame(rows).sort_values(
        ["f0_5", "average_precision", "precision", "modelo"],
        ascending=[False, False, False, True],
    )
    eligible = validation[validation.recall >= MIN_RECALL]
    if eligible.empty:
        raise ValueError("Nenhum candidato elegível")
    selected = eligible.iloc[0].modelo
    validation.to_csv(DEST / "validacao.csv", index=False)
    pd.concat(dev_predictions).to_csv(DEST / "scores_validacao.csv", index=False)
    selection = dict(
        selecionado=selected,
        limiares=thresholds,
        registrado_em_utc=datetime.now(timezone.utc).isoformat(),
        validacao_sha256=sha256(DEST / "validacao.csv"),
        modelo_sha256=sha256(STORE / "isolation_contextual.joblib"),
        criterio=protocol["configuracao"]["criterio"],
    )
    (DEST / "selecao_congelada.json").write_text(
        json.dumps(selection, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        "Seleção congelada:",
        selected,
        "; iniciando cinco testes reservados.",
        flush=True,
    )
    rows = []
    predictions = []
    for seed in TEST_SEEDS:
        _, adaptive, base, y, labels = prepare(context, seed, "teste")
        target = labels.set_index("id_transacao_natural").loc[adaptive.index]
        for name in CANDIDATES:
            scores = scores_for(
                name, adaptive, base, original_bundle, scaler, estimator
            )
            metrics = compute_metrics(y, scores, thresholds[name])
            metrics["f0_5"] = fbeta(metrics)
            rows.append(dict(seed=seed, modelo=name, **metrics))
            predictions.append(
                pd.DataFrame(
                    dict(
                        seed=seed,
                        modelo=name,
                        id_transacao_natural=adaptive.index,
                        data=adaptive.data,
                        y=y,
                        score=scores,
                        predicao=scores >= thresholds[name],
                        pico_legitimo=target.pico_legitimo.to_numpy(),
                        regime_novo=target.regime_novo.to_numpy(),
                        mecanismo=target.mecanismo.to_numpy(),
                        contexto_suficiente=adaptive.n_60d.to_numpy() >= 5,
                    )
                )
            )
        print("Teste concluído, seed", seed, flush=True)
    test = pd.DataFrame(rows)
    pred = pd.concat(predictions, ignore_index=True)
    test.to_csv(DEST / "teste_por_cliente.csv", index=False)
    pred.to_csv(DEST / "predicoes_teste.csv", index=False)
    aggregate = []
    for name, group in pred.groupby("modelo", sort=True):
        metrics = compute_metrics(group.y, group.score, thresholds[name])
        metrics["f0_5"] = fbeta(metrics)
        aggregate.append(dict(modelo=name, selecionado=name == selected, **metrics))
    aggregate = pd.DataFrame(aggregate)
    aggregate.to_csv(DEST / "teste_agregado.csv", index=False)
    # O lote já conhecido é apenas diagnóstico posterior, separado da avaliação reservada.
    history = read_input(DATASET / "historico_cliente.csv")
    batch = read_input(DATASET / "lote_cliente.csv")
    joined = pd.concat([history, batch])
    adaptive = (
        build_adaptive_features(joined)
        .set_index("id_transacao_natural")
        .loc[batch.id_transacao_natural]
    )
    base = (
        build_features(joined)
        .set_index("id_transacao_natural")
        .loc[batch.id_transacao_natural]
    )
    y = (
        pd.read_csv(DATASET / "gabarito_avaliacao.csv")
        .set_index("id_transacao_natural")
        .loc[batch.id_transacao_natural, "flag_anomalia"]
        .astype(int)
        .to_numpy()
    )
    known = []
    for name in ["Original congelado", selected]:
        scores = scores_for(name, adaptive, base, original_bundle, scaler, estimator)
        metrics = compute_metrics(y, scores, thresholds[name])
        metrics["f0_5"] = fbeta(metrics)
        known.append(dict(modelo=name, **metrics))
    pd.DataFrame(known).drop_duplicates("modelo").to_csv(
        DEST / "cliente_conhecido_diagnostico.csv", index=False
    )
    index = aggregate.set_index("modelo")
    old = index.loc["Original congelado"]
    new = index.loc[selected]
    improved = bool(
        new.precision > old.precision
        and new.f1 > old.f1
        and new.recall >= old.recall - 0.10
    )
    for name, digest in protocol["originais_sha256"].items():
        if sha256(ROOT / name) != digest:
            raise ValueError("Original modificado: " + name)
    summary = dict(
        selecionado=selected,
        melhoria_criterio_predefinido=improved,
        n_clientes_teste=len(TEST_SEEDS),
        limite="Cinco realizações do mesmo gerador sintético, sem cliente real",
        original=old.to_dict(),
        novo=new.to_dict(),
        originais_preservados=len(protocol["originais_sha256"]),
        datasets_sha256={
            str(p.relative_to(ROOT)): sha256(p) for p in STORE.rglob("*.csv")
        },
    )
    (DEST / "resumo.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "datasets_sha256"},
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    from .improvement_report import build_report

    build_report()


if __name__ == "__main__":
    run()
