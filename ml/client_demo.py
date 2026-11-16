"""Gera um cliente sintético e avalia a inferência em lote com modelo congelado."""

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .config import ARTIFACTS, REPORTS, ROOT
from .data import load_tables, sha256
from .evaluation import compute_metrics
from .features import REQUIRED, build_features
from .modeling import score_bundle
from .robustness.run import original_files

DATASET = ROOT / "ml/datasets/cliente_dummy_01"
DESTINATION = REPORTS / "cliente_dummy/rodada_01"
CONFIG = dict(
    seed=731927,
    parceiros_recorrentes=100,
    parceiros_novos=20,
    historico_inicio="2026-01-01",
    historico_fim="2026-03-31",
    lote_inicio="2026-04-01",
    lote_fim="2026-04-30",
    probabilidade_anomalia=0.04,
    fracao_sutil=0.5,
    probabilidade_pico_legitimo=0.015,
    fracao_regime=0.15,
    fator_regime=1.6,
    sigma_log_min=0.12,
    sigma_log_max=0.28,
    probabilidade_diaria_min=0.35,
    probabilidade_diaria_max=0.85,
)


def read_input(path):
    """Contrato do upload: sete campos; BRL; IDs textuais; sem gabarito."""
    frame = pd.read_csv(
        path, dtype={c: str for c in REQUIRED if c not in ["data", "valor_bruto"]}
    )
    if set(frame.columns) != set(REQUIRED):
        raise ValueError(
            "CSV deve conter somente os sete campos do contrato, sem gabarito ou atributos extras"
        )
    frame["data"] = pd.to_datetime(frame.data, errors="raise")
    frame["valor_bruto"] = pd.to_numeric(frame.valor_bruto, errors="raise")
    if (
        frame.empty
        or frame[REQUIRED].isna().any().any()
        or frame.id_transacao_natural.duplicated().any()
        or not np.isfinite(frame.valor_bruto).all()
        or (frame.valor_bruto <= 0).any()
        or not frame.tipo_transacao.isin(["RECEITA", "DESPESA"]).all()
    ):
        raise ValueError(
            "CSV vazio ou com campos inválidos, valores não positivos ou IDs duplicados"
        )
    if any(
        frame[c].str.strip().eq("").any()
        for c in REQUIRED
        if c not in ["data", "valor_bruto"]
    ):
        raise ValueError("Identificador ou tipo vazio")
    if not frame.data.eq(frame.data.dt.normalize()).all():
        raise ValueError("O contrato usa datas sem horário")
    return frame[REQUIRED]


def predict_frames(history, batch, bundle, threshold):
    """Scoring independente do gabarito; contexto online, sem treinar."""
    if history.data.max() >= batch.data.min():
        raise ValueError("Todo o histórico deve ser anterior ao início do lote")
    if set(history.id_transacao_natural) & set(batch.id_transacao_natural):
        raise ValueError("Histórico e lote não podem compartilhar IDs de transação")
    features = build_features(pd.concat([history, batch], ignore_index=True))
    features = features[
        features.id_transacao_natural.isin(batch.id_transacao_natural)
    ].copy()
    scores = score_bundle(bundle, features)
    if not np.isfinite(scores).all():
        raise ValueError("Scores não finitos")
    output = features[REQUIRED + ["qtd_historico", "sem_historico"]].copy()
    output["score"] = scores
    output["limiar"] = float(threshold)
    output["alerta"] = scores >= threshold
    output["contexto_suficiente"] = features.qtd_historico.to_numpy() >= 5
    output["parceiro_novo_no_lote"] = ~output.id_parceiro_natural.isin(
        history.id_parceiro_natural
    )
    # Score zero por falta de histórico não confirma normalidade.
    output["situacao"] = np.where(
        ~output.contexto_suficiente,
        "CONTEXTO_INSUFICIENTE",
        np.where(output.alerta, "REVISAR", "SEM_ALERTA"),
    )
    return output.sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)


def selected_model():
    selection = json.loads(
        (REPORTS / "selecao_validacao.json").read_text(encoding="utf-8")
    )
    calibration = pd.read_csv(REPORTS / "metricas_validacao.csv").set_index("modelo")
    name = selection["selecionado"]
    row = calibration.loc[name]
    model_path = ARTIFACTS / row.arquivo
    if sha256(model_path) != selection["modelos"][name]["sha256"]:
        raise ValueError("Modelo difere do artefato selecionado na validação")
    return name, model_path, float(row.limiar)


def freeze_protocol():
    """Registra desenho e dependências antes de gerar ou pontuar dados."""
    name, model_path, threshold = selected_model()
    reference = json.loads(
        (REPORTS / "robustness/rodada_01/protocolo_registrado.json").read_text(
            encoding="utf-8"
        )
    )
    originals = original_files()
    if originals != reference["originais_sha256"]:
        raise ValueError("Artefatos originais mudaram desde a auditoria")
    files = [
        Path(__file__),
        ROOT / "ml/client_demo_report.py",
        ROOT / "ml/features.py",
        ROOT / "ml/modeling.py",
        ROOT / "ml/evaluation.py",
        model_path,
        REPORTS / "selecao_validacao.json",
        REPORTS / "metricas_validacao.csv",
    ]
    current = dict(
        configuracao=CONFIG,
        modelo=name,
        limiar=threshold,
        regras="CSV sintético novo; modelo selecionado congelado; sem recalibração; contexto online de dias anteriores",
        codigo_e_modelos_sha256={str(p.relative_to(ROOT)): sha256(p) for p in files},
        originais_sha256=originals,
        versoes={
            p: importlib.metadata.version(p)
            for p in ["numpy", "pandas", "scikit-learn", "joblib"]
        },
    )
    DESTINATION.mkdir(parents=True, exist_ok=True)
    path = DESTINATION / "protocolo.json"
    if path.exists():
        previous = json.loads(path.read_text(encoding="utf-8"))
        if any(previous.get(k) != v for k, v in current.items()):
            raise ValueError(
                "Protocolo alterado: preserve rodada_01 e crie outra rodada explicitamente"
            )
        return previous
    current["registrado_em_utc"] = datetime.now(timezone.utc).isoformat()
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def generate_client_data(context, config=CONFIG):
    """Gerador próprio, sem reutilizar linhas do gerador original ou modelos.

    Context só fornece combinações válidas de códigos de área/categoria/tipo.
    Não há dependência de scores ou de estatísticas de valores do treino.
    """
    rng = np.random.RandomState(config["seed"])
    n_old, n_new = config["parceiros_recorrentes"], config["parceiros_novos"]
    partners = [f"DUMMY-P{i:03d}" for i in range(1, n_old + n_new + 1)]
    changed = set(
        rng.choice(
            partners[:n_old], round(n_old * config["fracao_regime"]), replace=False
        )
    )
    dates = pd.bdate_range(config["historico_inicio"], config["lote_fim"])
    contexts = (
        context[["tipo_transacao", "id_area_natural", "id_categoria_natural"]]
        .drop_duplicates()
        .sort_values(["tipo_transacao", "id_area_natural", "id_categoria_natural"])
        .reset_index(drop=True)
    )
    records, targets = [], []
    for i, partner in enumerate(partners):
        start = pd.Timestamp(
            config["lote_inicio"] if i >= n_old else config["historico_inicio"]
        )
        base_value = np.clip(rng.lognormal(np.log(2500), 1.1), 100, 60000)
        sigma = rng.uniform(config["sigma_log_min"], config["sigma_log_max"])
        probability = rng.uniform(
            config["probabilidade_diaria_min"], config["probabilidade_diaria_max"]
        )
        trend = rng.uniform(-0.0004, 0.0006)
        ctx = contexts.iloc[rng.randint(len(contexts))]
        for day in dates[dates >= start]:
            if rng.uniform() >= probability:
                continue
            day_number = (day - pd.Timestamp(config["historico_inicio"])).days
            seasonal = 1 + 0.04 * np.sin(2 * np.pi * day.dayofweek / 5)
            value = (
                base_value
                * np.exp(trend * day_number)
                * seasonal
                * rng.lognormal(-(sigma**2) / 2, sigma)
            )
            regime = partner in changed and day >= pd.Timestamp(config["lote_inicio"])
            if regime:
                value *= config["fator_regime"]
            anomaly = rng.uniform() < config["probabilidade_anomalia"]
            peak = not anomaly and rng.uniform() < config["probabilidade_pico_legitimo"]
            if peak:
                value *= rng.uniform(1.5, 2.5)
            legitimate_value = value
            mechanism, factor = "normal", 1.0
            if anomaly:
                subtle, inflation = (
                    rng.uniform() < config["fracao_sutil"],
                    rng.uniform() < 0.7,
                )
                mechanism = ("sutil_" if subtle else "ampla_") + (
                    "inflacao" if inflation else "reducao"
                )
                factor = (
                    rng.uniform(1.1, 1.3)
                    if subtle and inflation
                    else (
                        rng.uniform(0.7, 0.9)
                        if subtle
                        else (
                            rng.uniform(1.5, 2.5)
                            if inflation
                            else rng.uniform(0.35, 0.65)
                        )
                    )
                )
                value *= factor
            identifier = f"DUMMY-T{len(records) + 1:06d}"
            records.append(
                dict(
                    id_transacao_natural=identifier,
                    data=day,
                    id_parceiro_natural=partner,
                    valor_bruto=round(value, 2),
                    **ctx.to_dict(),
                )
            )
            targets.append(
                dict(
                    id_transacao_natural=identifier,
                    flag_anomalia=anomaly,
                    mecanismo=mechanism,
                    fator_aplicado=factor,
                    valor_legitimo=round(legitimate_value, 2),
                    pico_legitimo=peak,
                    regime_novo=regime,
                    parceiro_novo=i >= n_old,
                )
            )
    frame = (
        pd.DataFrame(records)[REQUIRED]
        .sort_values(["data", "id_transacao_natural"])
        .reset_index(drop=True)
    )
    labels = (
        pd.DataFrame(targets)
        .set_index("id_transacao_natural")
        .loc[frame.id_transacao_natural]
        .reset_index()
    )
    return (
        frame[frame.data < config["lote_inicio"]].copy(),
        frame[frame.data >= config["lote_inicio"]].copy(),
        labels,
    )


def evaluate_predictions(predictions, target):
    if target.id_transacao_natural.duplicated().any():
        raise ValueError("Gabarito duplicado")
    merged = predictions.merge(
        target, on="id_transacao_natural", validate="one_to_one", how="left"
    )
    if merged.flag_anomalia.isna().any():
        raise ValueError("Gabarito incompleto para o lote")
    threshold = float(merged.limiar.iloc[0])
    metrics = compute_metrics(merged.flag_anomalia.astype(int), merged.score, threshold)
    merged["resultado"] = np.select(
        [
            merged.alerta & merged.flag_anomalia,
            merged.alerta & ~merged.flag_anomalia,
            ~merged.alerta & merged.flag_anomalia,
        ],
        ["VP", "FP", "FN"],
        default="VN",
    )
    groups = {
        "Lote completo": pd.Series(True, index=merged.index),
        "Parceiros recorrentes": ~merged.parceiro_novo_no_lote,
        "Parceiros novos": merged.parceiro_novo_no_lote,
        "Contexto insuficiente (<5)": ~merged.contexto_suficiente,
        "Contexto suficiente (>=5)": merged.contexto_suficiente,
        "Adulterações amplas": merged.mecanismo.str.startswith("ampla"),
        "Adulterações sutis": merged.mecanismo.str.startswith("sutil"),
        "Normais com pico legítimo": merged.pico_legitimo & ~merged.flag_anomalia,
        "Normais em regime novo": merged.regime_novo & ~merged.flag_anomalia,
    }
    rows = []
    for name, mask in groups.items():
        subset = merged[mask]
        n_anomaly = int(subset.flag_anomalia.sum())
        n_normal = len(subset) - n_anomaly
        tp, fp = int((subset.resultado == "VP").sum()), int(
            (subset.resultado == "FP").sum()
        )
        rows.append(
            dict(
                segmento=name,
                n=len(subset),
                anomalias=n_anomaly,
                alertas=int(subset.alerta.sum()),
                tp=tp,
                fp=fp,
                recall=tp / n_anomaly if n_anomaly else np.nan,
                fpr=fp / n_normal if n_normal else np.nan,
            )
        )
    return metrics, pd.DataFrame(rows), merged


def run():
    protocol = freeze_protocol()
    context = load_tables()["fact_transacoes_financeiras"]
    history, batch, target = generate_client_data(context)
    if set(pd.concat([history, batch]).id_transacao_natural) & set(
        context.id_transacao_natural
    ):
        raise ValueError("Reuso de identificadores originais")
    DATASET.mkdir(parents=True, exist_ok=True)
    data = {
        "historico_cliente.csv": history,
        "lote_cliente.csv": batch,
        "gabarito_avaliacao.csv": target,
    }
    manifest_path = DATASET / "manifesto.json"
    if manifest_path.exists():
        previous = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(
            sha256(DATASET / name) != value
            for name, value in previous["arquivos_sha256"].items()
        ):
            raise ValueError(
                "Dataset dummy editado: preserve a versão e gere outra explicitamente"
            )
    for name, frame in data.items():
        payload = frame.to_csv(index=False, date_format="%Y-%m-%d", lineterminator="\n")
        path = DATASET / name
        if path.exists() and path.read_text(encoding="utf-8") != payload:
            raise ValueError(
                "Geração mudou: não sobrescreva o dataset dummy versionado"
            )
        path.write_text(payload, encoding="utf-8")
    manifest = dict(
        origem="Dados artificiais criados pelo SCAP; nenhum dado de cliente real",
        configuracao=CONFIG,
        linhas={k: len(v) for k, v in data.items()},
        moeda="BRL",
        gabarito="Somente avaliação posterior, nunca upload ou pontuação",
        arquivos_sha256={name: sha256(DATASET / name) for name in data},
    )
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # A inferência usa somente os CSVs de entrada.
    name, model_path, threshold = selected_model()
    predictions = predict_frames(
        read_input(DATASET / "historico_cliente.csv"),
        read_input(DATASET / "lote_cliente.csv"),
        joblib.load(model_path),
        threshold,
    )
    predictions.to_csv(
        DESTINATION / "predicoes_upload.csv", index=False, date_format="%Y-%m-%d"
    )
    # Abre o gabarito apenas após persistir as previsões.
    target = pd.read_csv(DATASET / "gabarito_avaliacao.csv")
    metrics, segments, merged = evaluate_predictions(predictions, target)
    (DESTINATION / "metricas.json").write_text(
        json.dumps(metrics, indent=2), encoding="utf-8"
    )
    segments.to_csv(DESTINATION / "segmentos.csv", index=False)
    merged.to_csv(
        DESTINATION / "avaliacao_com_gabarito.csv", index=False, date_format="%Y-%m-%d"
    )
    (DESTINATION / "integridade.json").write_text(
        json.dumps(
            dict(
                dataset_sha256=sha256(manifest_path),
                resultados_sha256={
                    p.name: sha256(p)
                    for p in [
                        DESTINATION / "predicoes_upload.csv",
                        DESTINATION / "metricas.json",
                        DESTINATION / "segmentos.csv",
                        DESTINATION / "avaliacao_com_gabarito.csv",
                    ]
                },
            ),
            indent=2,
        ),
        encoding="utf-8",
    )
    if original_files() != protocol["originais_sha256"]:
        raise ValueError("Um artefato original mudou durante a execução")
    from .client_demo_report import write_report, build_notebook

    write_report()
    from .notebooks import execute_notebooks

    execute_notebooks([build_notebook()])
    print(json.dumps(dict(modelo=name, **metrics), ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-only", action="store_true")
    parser.add_argument("--history", type=Path)
    parser.add_argument("--batch", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.score_only:
        if not all([args.history, args.batch, args.output]):
            parser.error("--score-only exige --history, --batch e --output")
        _, model_path, threshold = selected_model()
        output = predict_frames(
            read_input(args.history),
            read_input(args.batch),
            joblib.load(model_path),
            threshold,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        output.to_csv(args.output, index=False, date_format="%Y-%m-%d")
        print(
            f"Pontuadas {len(output)} transações; {output.alerta.sum()} alertas. Nenhum gabarito foi lido."
        )
    else:
        run()


if __name__ == "__main__":
    main()
