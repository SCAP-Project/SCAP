"""Treina e compara modelos com e sem contexto documental em clientes reservados."""
import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import precision_recall_curve, average_precision_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from .config import ROOT, REPORTS, ARTIFACTS
from .data import load_tables, sha256
from .evaluation import compute_metrics
from .context_data import (
    GENERATOR_CONFIG,
    INPUT_COLUMNS,
    generate_context_client,
    validate_context_input,
    degrade_documents,
)
from .context_model import (
    HISTORY_FEATURES,
    CONTEXT_FEATURES,
    build_context_features,
    score_candidate,
    predict_context,
)

DEST = REPORTS / "contexto/rodada_03"
STORE = ARTIFACTS / "contexto/rodada_03"
TRAIN_SEEDS = list(range(120001, 120007))
VAL_SEEDS = [220001, 220002, 220003]
TEST_SEEDS = [320001, 320002, 320003, 320004, 320005]
NAMES = [
    "Original congelado",
    "Mediana anterior",
    "Regra documental",
    "HGB sem contexto",
    "Logistica com contexto",
    "HGB com contexto",
]
HGB_PARAMETERS = dict(
    learning_rate=0.07,
    max_iter=150,
    max_leaf_nodes=15,
    min_samples_leaf=40,
    l2_regularization=1.0,
    early_stopping=False,
    random_state=42,
)
MIN_RECALL = 0.50


def dump(path, payload):
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def freeze():
    DEST.mkdir(parents=True, exist_ok=True)
    STORE.mkdir(parents=True, exist_ok=True)
    previous = json.loads(
        (REPORTS / "cliente_dummy/rodada_01/protocolo.json").read_text(encoding="utf-8")
    )["originais_sha256"]
    for p in (REPORTS / "melhoria/rodada_02").glob("*"):
        if p.is_file():
            previous[str(p.relative_to(ROOT))] = sha256(p)
    files = [
        ROOT / "ml" / n
        for n in [
            "context_data.py",
            "context_model.py",
            "context_run.py",
            "features.py",
            "adaptive_features.py",
            "evaluation.py",
        ]
    ]
    settings = dict(
        gerador=GENERATOR_CONFIG,
        treino_seeds=TRAIN_SEEDS,
        validacao_seeds=VAL_SEEDS,
        teste_seeds=TEST_SEEDS,
        treino="Março a junho/2026; seis clientes novos; históricos desde janeiro",
        validacao="Julho/2026; três outros clientes; históricos janeiro–junho",
        teste="Setembro/2026; cinco outros clientes; históricos janeiro–agosto",
        candidatos=NAMES,
        atributos_historicos=HISTORY_FEATURES,
        atributos_com_contexto=CONTEXT_FEATURES,
        parametros_hgb=HGB_PARAMETERS,
        logistica=dict(C=1.0, max_iter=1000, random_state=42),
        min_recall_validacao=MIN_RECALL,
        beta=0.5,
        min_alertas_validacao=20,
        criterio="Maior F0.5 na validação, recall>=50%; desempate AP, precisão e nome",
        sucesso="Precisão>=60% e recall>=50% no teste nominal, e AP/F1 maiores que HGB sem contexto nos mesmos lotes",
        testes_adversos=["documentos_degradados", "sem_documentos"],
        hipoteses="Pedido com quantidade e preço emitido antes do lançamento, com erros e ausência independentes da adulteração",
        limite="Nova hipótese de dados sintéticos; não corresponde a documentação real nem melhora retroativa na base antiga",
    )
    payload = dict(
        configuracao=settings,
        anteriores_sha256=previous,
        metodos_sha256={str(p.relative_to(ROOT)): sha256(p) for p in files},
        versoes={
            p: importlib.metadata.version(p)
            for p in ["numpy", "pandas", "scikit-learn", "scipy", "joblib"]
        },
    )
    path = DEST / "protocolo.json"
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        if any(old.get(k) != v for k, v in payload.items()):
            raise ValueError(
                "Protocolo mudou; preserve a rodada e crie outra explicitamente"
            )
        return old
    payload["registrado_em_utc"] = datetime.now(timezone.utc).isoformat()
    dump(path, payload)
    return payload


def read_source(path):
    frame = pd.read_csv(
        path,
        dtype={
            c: str
            for c in INPUT_COLUMNS
            if c
            not in [
                "data",
                "valor_bruto",
                "data_documento",
                "quantidade_documento",
                "preco_unitario_documento",
            ]
        },
    )
    return validate_context_input(frame)


def prepare(context, seed, stage):
    start, end = {
        "treino": ("2026-03-01", "2026-06-30"),
        "validacao": ("2026-07-01", "2026-07-31"),
        "teste": ("2026-09-01", "2026-09-30"),
    }[stage]
    folder = STORE / stage / f"seed_{seed}"
    folder.mkdir(parents=True, exist_ok=True)
    source, labels = generate_context_client(context, seed, start, end)
    source.to_csv(
        folder / "entrada.csv", index=False, date_format="%Y-%m-%d", lineterminator="\n"
    )
    labels.to_csv(folder / "gabarito.csv", index=False, lineterminator="\n")
    source = read_source(folder / "entrada.csv")
    features = build_context_features(source)
    features = features[features.data >= start].copy()
    y = (
        labels.set_index("id_transacao_natural")
        .loc[features.id_transacao_natural, "flag_anomalia"]
        .astype(int)
        .to_numpy()
    )
    return source, labels, features, y


def calibrate(y, scores):
    p, r, t = precision_recall_curve(y, scores)
    objective = 1.25 * p[:-1] * r[:-1] / np.maximum(0.25 * p[:-1] + r[:-1], 1e-12)
    ordered = np.sort(scores)
    counts = len(scores) - np.searchsorted(ordered, t, side="left")
    eligible = (r[:-1] >= MIN_RECALL) & (counts >= 20) & (t > 0)
    if not eligible.any():
        return None
    objective[~eligible] = -np.inf
    index = np.flatnonzero(np.isclose(objective, objective.max(), rtol=0, atol=1e-12))[
        -1
    ]
    return float(t[index])


def f05(m):
    return (
        1.25
        * m["precision"]
        * m["recall"]
        / max(0.25 * m["precision"] + m["recall"], 1e-12)
    )


def candidates():
    return {
        "Original congelado": dict(kind="historical", threshold=1.68124570988478),
        "Mediana anterior": dict(kind="median", threshold=2.7882026631890953),
        "Regra documental": dict(kind="document_rule"),
        "HGB sem contexto": dict(
            kind="learned",
            features=HISTORY_FEATURES,
            estimator=HistGradientBoostingClassifier(**HGB_PARAMETERS),
        ),
        "Logistica com contexto": dict(
            kind="learned",
            features=CONTEXT_FEATURES,
            estimator=make_pipeline(
                StandardScaler(),
                LogisticRegression(C=1.0, max_iter=1000, random_state=42),
            ),
        ),
        "HGB com contexto": dict(
            kind="learned",
            features=CONTEXT_FEATURES,
            estimator=HistGradientBoostingClassifier(**HGB_PARAMETERS),
        ),
    }


def train_and_select(context):
    print("Gerando seis clientes de treino...", flush=True)
    training = []
    targets = []
    for seed in TRAIN_SEEDS:
        _, _, features, y = prepare(context, seed, "treino")
        training.append(features)
        targets.append(y)
        print("Treino preparado:", seed, len(features), flush=True)
    train = pd.concat(training, ignore_index=True)
    ytrain = np.concatenate(targets)
    print("Gerando validação, sem abrir testes...", flush=True)
    validation = []
    targets = []
    for seed in VAL_SEEDS:
        _, _, features, y = prepare(context, seed, "validacao")
        validation.append(features)
        targets.append(y)
        print("Validação preparada:", seed, len(features), flush=True)
    validation = pd.concat(validation, ignore_index=True)
    yval = np.concatenate(targets)
    bundles = candidates()
    rows = []
    predictions = []
    for number, (name, bundle) in enumerate(bundles.items()):
        print("Ajustando candidato:", name, flush=True)
        with threadpool_limits(limits=1):
            if bundle["kind"] == "learned":
                bundle["estimator"].fit(train[bundle["features"]], ytrain)
            scores = score_candidate(bundle, validation)
        threshold = bundle.get("threshold")
        if threshold is None:
            threshold = calibrate(yval, scores)
        if threshold is None:
            threshold = float(np.nextafter(scores.max(), np.inf))
            eligible = False
        else:
            eligible = True
        metrics = compute_metrics(yval, scores, threshold)
        metrics["f0_5"] = f05(metrics)
        bundle["threshold"] = threshold
        bundle["name"] = name
        path = STORE / f"candidato_{number}.joblib"
        joblib.dump(bundle, path)
        rows.append(
            dict(
                modelo=name,
                arquivo=path.name,
                elegivel=eligible and metrics["recall"] >= MIN_RECALL,
                **metrics,
            )
        )
        predictions.append(
            pd.DataFrame(
                dict(
                    modelo=name,
                    id_transacao_natural=validation.id_transacao_natural,
                    y=yval,
                    score=scores,
                )
            )
        )
    result = pd.DataFrame(rows).sort_values(
        ["f0_5", "average_precision", "precision", "modelo"],
        ascending=[False, False, False, True],
    )
    eligible = result[result.elegivel]
    if eligible.empty:
        raise ValueError("Nenhum modelo atende ao recall de validação")
    winner = eligible.iloc[0]
    result.to_csv(DEST / "validacao.csv", index=False)
    pd.concat(predictions).to_csv(DEST / "scores_validacao.csv", index=False)
    selection = dict(
        selecionado=winner.modelo,
        arquivo=winner.arquivo,
        limiar=float(winner.limiar),
        registrado_em_utc=datetime.now(timezone.utc).isoformat(),
        n_treino=len(train),
        positivos_treino=int(ytrain.sum()),
        n_validacao=len(validation),
        modelos_sha256={
            name: sha256(STORE / row["arquivo"])
            for name, row in result.set_index("modelo").to_dict("index").items()
        },
        validacao_sha256=sha256(DEST / "validacao.csv"),
        criterio="F0.5 com recall>=50% na validação",
    )
    dump(DEST / "selecao_congelada.json", selection)
    print("SELEÇÃO CONGELADA:", winner.modelo, flush=True)
    return selection, bundles


def evaluate_reserved(context, selection, bundles):
    rows = []
    predictions = []
    for seed in TEST_SEEDS:
        source, labels, nominal, y = prepare(context, seed, "teste")
        targets = labels.set_index("id_transacao_natural").loc[
            nominal.id_transacao_natural
        ]
        scenarios = {"nominal": nominal}
        for scenario in ["documentos_degradados", "sem_documentos"]:
            degraded = degrade_documents(source, seed, scenario)
            features = build_context_features(degraded)
            scenarios[scenario] = features[features.data >= "2026-09-01"].copy()
        for scenario, features in scenarios.items():
            assert np.array_equal(
                features.id_transacao_natural, nominal.id_transacao_natural
            )
            for name, bundle in bundles.items():
                with threadpool_limits(limits=1):
                    scores = score_candidate(bundle, features)
                metrics = compute_metrics(y, scores, bundle["threshold"])
                metrics["f0_5"] = f05(metrics)
                rows.append(dict(seed=seed, cenario=scenario, modelo=name, **metrics))
                predictions.append(
                    pd.DataFrame(
                        dict(
                            seed=seed,
                            cenario=scenario,
                            modelo=name,
                            id_transacao_natural=features.id_transacao_natural,
                            data=features.data,
                            y=y,
                            score=scores,
                            predicao=scores >= bundle["threshold"],
                            documento_disponivel=features.sem_documento.eq(0),
                            pico_legitimo=targets.pico_legitimo.to_numpy(),
                            regime_novo=targets.regime_novo.to_numpy(),
                            mecanismo=targets.mecanismo.to_numpy(),
                            erro_documento=targets.erro_documento.to_numpy(),
                        )
                    )
                )
        print("Teste reservado concluído:", seed, len(nominal), flush=True)
    individual = pd.DataFrame(rows)
    pred = pd.concat(predictions, ignore_index=True)
    individual.to_csv(DEST / "teste_por_cliente.csv", index=False)
    pred.to_csv(DEST / "predicoes_teste.csv", index=False, date_format="%Y-%m-%d")
    aggregate = []
    for (scenario, name), group in pred.groupby(["cenario", "modelo"], sort=True):
        metrics = compute_metrics(group.y, group.score, bundles[name]["threshold"])
        metrics["f0_5"] = f05(metrics)
        aggregate.append(
            dict(
                cenario=scenario,
                modelo=name,
                selecionado=name == selection["selecionado"],
                **metrics,
            )
        )
    aggregate = pd.DataFrame(aggregate)
    aggregate.to_csv(DEST / "teste_agregado.csv", index=False)
    segments = []
    for scenario in ["nominal", "documentos_degradados", "sem_documentos"]:
        group = pred[
            (pred.cenario == scenario) & (pred.modelo == selection["selecionado"])
        ]
        masks = {
            "Lote completo": np.ones(len(group), bool),
            "Com documento": group.documento_disponivel,
            "Sem documento": ~group.documento_disponivel,
            "Adulterações sutis": group.mecanismo.str.startswith("sutil"),
            "Adulterações amplas": group.mecanismo.str.startswith("ampla"),
            "Normais com pico legítimo": group.pico_legitimo & (group.y == 0),
            "Normais em regime novo": group.regime_novo & (group.y == 0),
            "Normais com erro documental": group.erro_documento & (group.y == 0),
        }
        for name, mask in masks.items():
            subset = group.loc[np.asarray(mask)]
            positive = int(subset.y.sum())
            normal = len(subset) - positive
            tp = int((subset.predicao & (subset.y == 1)).sum())
            fp = int((subset.predicao & (subset.y == 0)).sum())
            segments.append(
                dict(
                    cenario=scenario,
                    segmento=name,
                    n=len(subset),
                    anomalias=positive,
                    tp=tp,
                    fp=fp,
                    precision=tp / max(tp + fp, 1),
                    recall=tp / positive if positive else np.nan,
                    fpr=fp / normal if normal else np.nan,
                )
            )
    pd.DataFrame(segments).to_csv(DEST / "segmentos.csv", index=False)
    index = aggregate[aggregate.cenario == "nominal"].set_index("modelo")
    winner = index.loc[selection["selecionado"]]
    control = index.loc["HGB sem contexto"]
    success = bool(
        winner.precision >= 0.60
        and winner.recall >= 0.50
        and winner.average_precision > control.average_precision
        and winner.f1 > control.f1
    )
    summary = dict(
        selecionado=selection["selecionado"],
        criterio_sucesso_atendido=success,
        nominal=winner.to_dict(),
        controle_sem_contexto=control.to_dict(),
        cenarios_selecionado=aggregate[aggregate.selecionado].to_dict("records"),
        limite="Hipótese de referência documental sintética disponível antes do lançamento; não é validação empresarial",
        teste_seeds=TEST_SEEDS,
        datasets_sha256={
            str(p.relative_to(ROOT)): sha256(p) for p in STORE.rglob("*.csv")
        },
    )
    # Controle negativo descritivo, sem modificar a seleção ou os limiares.
    group = pred[
        (pred.cenario == "nominal") & (pred.modelo == selection["selecionado"])
    ]
    rng = np.random.default_rng(88231)
    summary["controle_negativo_ap"] = float(
        np.mean(
            [
                average_precision_score(rng.permutation(group.y), group.score)
                for _ in range(50)
            ]
        )
    )
    dump(DEST / "resumo.json", summary)
    return summary


def score_only(history, batch, output):
    selection = json.loads(
        (DEST / "selecao_congelada.json").read_text(encoding="utf-8")
    )
    path = STORE / selection["arquivo"]
    if sha256(path) != selection["modelos_sha256"][selection["selecionado"]]:
        raise ValueError("Modelo foi alterado")
    bundle = joblib.load(path)
    result = predict_context(
        read_source(history), read_source(batch), bundle, selection["limiar"]
    )
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(output, index=False, date_format="%Y-%m-%d")
    print("Inferência sem gabarito:", output, len(result), flush=True)


def run():
    protocol = freeze()
    context = load_tables()["fact_transacoes_financeiras"]
    selection, bundles = train_and_select(context)
    summary = evaluate_reserved(context, selection, bundles)
    for name, expected in protocol["anteriores_sha256"].items():
        if sha256(ROOT / name) != expected:
            raise ValueError("Resultado anterior foi alterado: " + name)
    dump(
        DEST / "integridade.json",
        dict(
            anteriores_preservados=len(protocol["anteriores_sha256"]),
            resultados_sha256={
                p.name: sha256(p)
                for p in DEST.glob("*")
                if p.is_file() and p.name != "integridade.json"
            },
        ),
    )
    print(
        json.dumps(
            {
                k: v
                for k, v in summary.items()
                if k not in ["datasets_sha256", "cenarios_selecionado"]
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )
    from .context_report import build_report

    build_report()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--history", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.score_only:
        if not all([args.history, args.batch, args.output]):
            parser.error("Informe --history, --batch e --output")
        score_only(args.history, args.batch, args.output)
    else:
        run()
