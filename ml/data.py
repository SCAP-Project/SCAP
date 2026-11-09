"""Leitura das tabelas, verificacao do snapshot e rotulos so para avaliacao."""

import hashlib
import json
from pathlib import Path

import pandas as pd

from .config import DATA_DIR


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_tables(data_dir=DATA_DIR):
    data_dir = Path(data_dir)
    paths = sorted((data_dir / "refined").glob("*.csv"))
    if len(paths) != 10:
        raise FileNotFoundError("Esperadas dez tabelas refined. Execute python -m etl.csv_pipeline --generate")
    manifest = json.loads((data_dir / "exports/etl_manifest.json").read_text(encoding="utf-8"))
    result = {}
    for path in paths:
        if sha256(path) != manifest["outputs"][f"refined/{path.name}"]:
            raise ValueError(f"Snapshot alterado: {path.name}; reexecute o ETL")
        identifiers = {c: str for c in pd.read_csv(path, nrows=0).columns if c.startswith("id_") or c == "codigo_iso"}
        frame = pd.read_csv(path, dtype=identifiers)
        if "data" in frame:
            frame["data"] = pd.to_datetime(frame.data)
        result[path.stem] = frame
    return result


def load_labels(ids=None, data_dir=DATA_DIR):
    path = Path(data_dir) / "ground_truth/transacoes_gabarito.csv"
    frame = pd.read_csv(path, dtype={"id_transacao_raw": str})
    if frame.id_transacao_raw.duplicated().any():
        raise ValueError("Gabarito com chave duplicada")
    if ids is not None:
        index = pd.Index(ids)
        frame = frame.set_index("id_transacao_raw").reindex(index)
        if frame.flag_anomalia.isna().any():
            raise ValueError("Rotulo ausente para alguma transacao")
        frame.index.name = "id_transacao_natural"
        frame = frame.reset_index()
    return frame
