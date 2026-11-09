"""python -m ml.robustness.run: auditoria, novos cenarios e ablacoes."""

import argparse
from datetime import datetime, timezone
import json
import importlib.metadata
import re
import sys

import joblib
import pandas as pd

from ml.config import ARTIFACTS, DATA_DIR, REPORTS, ROOT
from ml.data import sha256
from ml.evaluation import compute_metrics
from ml.features import build_features
from ml.modeling import score_bundle
from ml.split import assign_periods
from .ablations import FEATURE_GROUPS, run_ablations
from .audit import run_audit
from .scenarios import SEEDS, SCENARIOS, apply_scenario, generate_replication

DESTINATION = REPORTS / "robustness/rodada_01"
DATASETS = ARTIFACTS / "robustness/rodada_01"


def assert_protocol_matches(previous, current):
    for key in ["originais_sha256", "configuracao", "metodos_sha256", "versoes"]:
        if previous.get(key) != current[key]:
            raise ValueError(f"O protocolo mudou ({key}); use um novo --run-id e preserve a rodada anterior")


def method_hashes():
    files = [ROOT / "ml" / name for name in ["config.py", "data.py", "features.py", "modeling.py", "evaluation.py", "split.py", "experiment.py"]]
    files += [ROOT / "ml/robustness" / name for name in ["scenarios.py", "audit.py", "ablations.py", "run.py"]]
    return {str(p.relative_to(ROOT)): sha256(p) for p in files}


def original_files():
    files = [p for folder in [ARTIFACTS, REPORTS, DATA_DIR / "refined", DATA_DIR / "ground_truth"] for p in folder.glob("*") if p.is_file()]
    files += [ROOT / "etl/data_generation/generators/dados_transacoes_financeiras.ipynb"]
    return {str(p.relative_to(ROOT)): sha256(p) for p in sorted(files)}


def freeze_protocol():
    DESTINATION.mkdir(parents=True, exist_ok=True)
    DATASETS.mkdir(parents=True, exist_ok=True)
    frozen = original_files()
    settings = dict(seeds=SEEDS, cenarios=SCENARIOS, grupos_atributos=FEATURE_GROUPS,
                    corte_teste="2025-07-01", recalibracao_nos_desafios=False,
                    regras="Modelos e limiares originais; cenarios pareados; ablacoes apenas diagnosticas")
    # Converte tuplas para a mesma representacao JSON em reexecucoes.
    settings = json.loads(json.dumps(settings))
    path = DESTINATION / "protocolo_registrado.json"
    report = dict(registrado_em_utc=datetime.now(timezone.utc).isoformat(), configuracao=settings,
                  originais_sha256=frozen, registro="Registro local antes da execucao; nao e pre-registro externo",
                  metodos_sha256=method_hashes(),
                  versoes={p: importlib.metadata.version(p) for p in ["numpy", "pandas", "scikit-learn", "scipy", "joblib"]})
    report["versoes"]["python"] = sys.version
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        assert_protocol_matches(previous, report)
        return previous
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def run_challenges():
    calibration = pd.read_csv(REPORTS / "metricas_validacao.csv")
    bundles = {row.modelo: joblib.load(ARTIFACTS / row.arquivo) for row in calibration.itertuples()}
    rows, all_predictions, checksums = [], [], {}
    for seed in SEEDS:
        print(f"Gerando replicacao independente seed={seed}...", flush=True)
        base, labels = generate_replication(seed)
        for scenario in SCENARIOS:
            print(f"Avaliando seed={seed} / {scenario} (pesos e limiares congelados)...", flush=True)
            source, target = apply_scenario(base, labels, scenario, seed)
            prefix = DATASETS / f"seed{seed}_{scenario}"
            source_path, label_path = prefix.with_name(prefix.name + "_transacoes.csv"), prefix.with_name(prefix.name + "_gabarito.csv")
            source.to_csv(source_path, index=False, date_format="%Y-%m-%d")
            target.to_csv(label_path, index=False)
            checksums[source_path.name] = sha256(source_path)
            checksums[label_path.name] = sha256(label_path)
            # Pontuar exatamente os valores persistidos, sem depender de precisao
            # adicional que nao seria recuperada pelo leitor do dataset.
            source = pd.read_csv(source_path, dtype={"id_transacao_natural": str, "id_parceiro_natural": str, "id_categoria_natural": str, "id_area_natural": str}, parse_dates=["data"])
            features = build_features(source)
            test = features[assign_periods(features) == "teste"].copy().reset_index(drop=True)
            aligned = target.set_index("id_transacao_natural").loc[test.id_transacao_natural]
            y = aligned.flag_anomalia.astype(int).to_numpy()
            legitimate = aligned.evento_legitimo.to_numpy(dtype=bool)
            regime = aligned.regime_novo.to_numpy(dtype=bool)
            for row in calibration.itertuples():
                scores = score_bundle(bundles[row.modelo], test)
                predicted = scores >= row.limiar
                normal = y == 0
                counts = dict(n_extremos_legitimos=int(legitimate.sum()),
                              fpr_extremos_legitimos=float(predicted[legitimate].mean()) if legitimate.any() else 0.0,
                              fpr_normais_regime=float(predicted[normal & regime].mean()) if (normal & regime).any() else 0.0,
                              fpr_normais=float(predicted[normal].mean()))
                rows.append(dict(seed=seed, cenario=scenario, modelo=row.modelo, **compute_metrics(y, scores, row.limiar), **counts))
                output = pd.DataFrame(dict(seed=seed, cenario=scenario, modelo=row.modelo,
                                          id_transacao_natural=test.id_transacao_natural, data=test.data,
                                          y=y, score=scores, predicao=predicted,
                                          evento_legitimo=legitimate, regime_novo=regime))
                all_predictions.append(output)
    result = pd.DataFrame(rows)
    result.to_csv(DESTINATION / "metricas_desafios.csv", index=False)
    pd.concat(all_predictions, ignore_index=True).to_csv(DESTINATION / "predicoes_desafios.csv", index=False, date_format="%Y-%m-%d")
    (DESTINATION / "datasets_sha256.json").write_text(json.dumps(checksums, indent=2), encoding="utf-8")
    return result


def assert_originals_preserved(protocol):
    unchanged = original_files() == protocol["originais_sha256"]
    (DESTINATION / "preservacao_originais.json").write_text(json.dumps(dict(originais_preservados=unchanged, arquivos_conferidos=len(protocol["originais_sha256"])), indent=2), encoding="utf-8")
    if not unchanged:
        raise ValueError("Um artefato original foi modificado durante a auditoria")


def main():
    global DESTINATION, DATASETS
    parser = argparse.ArgumentParser(description="SCAP: auditoria e robustez sem modificar o experimento original")
    parser.add_argument("--stage", choices=["all", "audit", "challenges", "ablations", "report", "notebooks"], default="all")
    parser.add_argument("--run-id", default="rodada_01", help="Pasta de uma rodada; codigo/metodo diferente exige outra pasta")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.run_id):
        parser.error("--run-id deve conter apenas letras, numeros, hifen ou underscore")
    DESTINATION = REPORTS / "robustness" / args.run_id
    DATASETS = ARTIFACTS / "robustness" / args.run_id
    protocol = freeze_protocol()
    if args.stage in ["all", "audit"]:
        audit = run_audit(DESTINATION)
        if not audit["todos_aprovados"]:
            raise ValueError("Auditoria encontrou divergencias; confira auditoria.json antes de continuar")
    if args.stage in ["all", "challenges"]:
        run_challenges()
    if args.stage in ["all", "ablations"]:
        run_ablations(DESTINATION, DATASETS / "ablations")
    if args.stage in ["all", "report"]:
        from .report import write_report, make_figures
        write_report(DESTINATION)
        make_figures(DESTINATION)
    if args.stage in ["all", "notebooks"]:
        from .notebooks import build_notebooks
        from ml.notebooks import execute_notebooks
        execute_notebooks(build_notebooks(DESTINATION))
    assert_originals_preserved(protocol)
    print("Auditoria/robustez concluida; artefatos originais preservados.")


if __name__ == "__main__":
    main()
