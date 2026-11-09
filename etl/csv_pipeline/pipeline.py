"""Leitura, validacao e publicacao das camadas CSV locais."""

from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

import pandas as pd

from .refined import build_refined
from .trusted import REQUIRED, build_trusted
from .validation import validate_refined


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(staging, data_dir, relatives):
    """Restaura a geracao anterior se uma substituicao falhar."""
    replaced = []
    backups = staging / "backup"
    for relative in relatives:
        target = data_dir / relative
        if target.exists():
            backup = backups / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target, backup)
    try:
        for relative in relatives:
            target = data_dir / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, target)
            replaced.append(relative)
    except OSError:
        for relative in reversed(replaced):
            backup, target = backups / relative, data_dir / relative
            if backup.exists():
                shutil.copyfile(backup, target)
            else:
                target.unlink()
        raise


def verify_previous(data_dir, observed_on):
    manifest_path = data_dir / "exports/etl_manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if observed_on.isoformat() < manifest["observed_on"]:
        raise ValueError("Data de observacao anterior a ultima execucao")
    for relative, expected in manifest["outputs"].items():
        path = (data_dir / relative).resolve()
        if not path.is_relative_to(data_dir) or not path.is_file() or checksum(path) != expected:
            raise ValueError(f"Saida alterada ou incompleta: {relative}; restaure a ultima geracao valida")


def read_raw(data_dir):
    frames, paths = {}, []
    for entity in REQUIRED:
        files = sorted((data_dir / "raw" / entity).glob("*.csv"))
        if not files:
            raise FileNotFoundError(f"CSV obrigatorio ausente: raw/{entity}/*.csv")
        frames[entity] = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False) for p in files], ignore_index=True)
        paths.extend(files)
    return frames, paths


def run_pipeline(data_dir: Path, observed_on=None, validate_only=False):
    """Valida todas as camadas em memoria antes de substituir qualquer saida.

    As dimensoes anteriores preservam historico e as chaves dos fatos.
    O manifesto e publicado por ultimo e identifica entradas e saidas.
    """
    data_dir = Path(data_dir).resolve()
    observed_on = observed_on or date.today()
    verify_previous(data_dir, observed_on)
    raw, inputs = read_raw(data_dir)
    previous = {p.stem: pd.read_csv(p, dtype=str, keep_default_na=False)
                for p in (data_dir / "trusted").glob("*.csv")}
    trusted = build_trusted(raw, previous, observed_on)
    refined = build_refined(trusted)
    validate_refined(refined)
    ground_truth = data_dir / "ground_truth/transacoes_gabarito.csv"
    if ground_truth.is_file():
        labels = pd.read_csv(ground_truth, dtype=str, keep_default_na=False)
        if labels.id_transacao_raw.duplicated().any() or set(labels.id_transacao_raw) != set(raw["transacoes_financeiras"].id_transacao_raw):
            raise ValueError("Gabarito nao corresponde as transacoes locais")
        inputs.append(ground_truth)
    manifest = {
        "executed_at_utc": datetime.now(timezone.utc).isoformat(),
        "observed_on": observed_on.isoformat(),
        "storage": "csv", "financial_unit": "BRL/USD/EUR separados por moeda_sk",
        "history_policy": "SCD2 diario por observacao; correcoes no mesmo dia consolidam a versao",
        "inputs": {str(p.relative_to(data_dir)): checksum(p) for p in inputs},
        "counts": {f"{layer}.{name}": len(frame) for layer, tables in [("raw", raw), ("trusted", trusted), ("refined", refined)] for name, frame in tables.items()},
        "outputs": {},
    }
    if validate_only:
        return manifest
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".etl-staging-", dir=data_dir) as directory:
        staging = Path(directory).resolve()
        for layer, tables in [("trusted", trusted), ("refined", refined)]:
            (staging / layer).mkdir()
            for name, frame in tables.items():
                path = staging / layer / f"{name}.csv"
                frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
                manifest["outputs"][f"{layer}/{name}.csv"] = checksum(path)
        (staging / "exports").mkdir()
        manifest_path = staging / "exports/etl_manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        publish(staging, data_dir, list(manifest["outputs"]) + ["exports/etl_manifest.json"])
    return manifest
