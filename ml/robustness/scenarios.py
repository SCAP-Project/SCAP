"""Replicacoes sinteticas e cenarios definidos antes de observar seus scores."""

import contextlib
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ml.config import ROOT
from ml.features import REQUIRED

SEEDS = [101, 202, 303]
SCENARIOS = {
    "original": dict(sutil=False, ruido=0.0, extremos=0.0, regime=0.0),
    "sutis": dict(sutil=True, ruido=0.0, extremos=0.0, regime=0.0),
    "extremos_legitimos": dict(sutil=False, ruido=0.0, extremos=0.05, regime=0.0),
    "mudanca_regime": dict(sutil=False, ruido=0.0, extremos=0.0, regime=0.30),
    "combinado": dict(sutil=True, ruido=0.25, extremos=0.05, regime=0.30),
}


def generate_replication(seed):
    """Executa o gerador original em memoria, sem a celula de exportacao.

    Somente a seed e alterada. Valores antes da injecao sao recuperados por
    chave natural do gabarito, para aplicar os desafios de forma pareada.
    """
    path = ROOT / "etl/data_generation/generators/dados_transacoes_financeiras.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    namespace = {"display": lambda *args, **kwargs: None}
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
        for index, cell in enumerate(notebook["cells"][:-1]):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell["source"])
            if index == 0:
                if source.count("seed = 42") != 1:
                    raise ValueError("Configuracao do gerador mudou; revise o adaptador")
                source = source.replace("seed = 42", f"seed = {int(seed)}")
            if "to_csv(" in source:
                raise ValueError("O adaptador nao pode exportar fontes originais")
            exec(compile(source, f"replicacao_seed{seed}_cell{index}", "exec"), namespace)
    generated = namespace["df_pgtos"].copy().rename(columns={
        "id_transacao_raw": "id_transacao_natural", "id_fornecedor_raw": "id_parceiro_natural",
        "data_transacao": "data", "codigo_area_raw": "id_area_natural", "id_categoria_raw": "id_categoria_natural"})
    labels = namespace["df_gabarito"].rename(columns={"id_transacao_raw": "id_transacao_natural"}).copy()
    original_values = namespace["df_base_normal"].set_index("id_transacao_raw").valor_bruto
    generated["valor_bruto"] = generated.id_transacao_natural.map(original_values)
    generated = generated[REQUIRED].copy()
    generated["data"] = pd.to_datetime(generated.data)
    for col in ["id_parceiro_natural", "id_transacao_natural"]:
        generated[col] = f"S{seed}-" + generated[col].astype(str)
    labels["id_transacao_natural"] = f"S{seed}-" + labels.id_transacao_natural.astype(str)
    generated["id_categoria_natural"] = generated.id_categoria_natural.astype(str)
    return generated, labels[["id_transacao_natural", "flag_anomalia", "fator_aplicado"]]


def apply_scenario(base, labels, scenario, seed):
    config = SCENARIOS[scenario]
    frame = base[REQUIRED].copy().reset_index(drop=True)
    if frame.id_transacao_natural.duplicated().any() or labels.id_transacao_natural.duplicated().any():
        raise ValueError("Chave duplicada no cenario")
    targets = labels.set_index("id_transacao_natural").reindex(frame.id_transacao_natural).reset_index()
    if targets.flag_anomalia.isna().any():
        raise ValueError("Gabarito incompleto no cenario")
    targets["flag_anomalia"] = targets.flag_anomalia.astype(bool)
    positive = targets.flag_anomalia.to_numpy()
    noise_rng = np.random.RandomState(seed + 9001)
    event_rng = np.random.RandomState(seed + 9002)
    regime_rng = np.random.RandomState(seed + 9003)
    factor_rng = np.random.RandomState(seed + 9004)
    values = frame.valor_bruto.to_numpy(dtype=float).copy()
    # Ruido extra afeta valores legitimos antes de qualquer adulteracao.
    values *= noise_rng.lognormal(-config["ruido"] ** 2 / 2, config["ruido"], len(frame))
    event_draw = event_rng.uniform(size=len(frame))
    event_factors = event_rng.uniform(1.5, 3.5, len(frame))
    legitimate = (event_draw < config["extremos"]) & ~positive
    values[legitimate] *= event_factors[legitimate]
    partners = np.sort(frame.id_parceiro_natural.unique())
    changed = regime_rng.choice(partners, size=int(round(len(partners) * config["regime"])), replace=False)
    regime = frame.id_parceiro_natural.isin(changed) & (pd.to_datetime(frame.data) >= "2025-07-01")
    values[regime] *= 1.8
    legitimate_values = values.copy()
    factors = targets.fator_aplicado.to_numpy(dtype=float).copy()
    if config["sutil"]:
        inflation = positive & (factors > 1)
        reduction = positive & ~inflation
        factors[inflation] = factor_rng.uniform(1.1, 1.3, inflation.sum())
        factors[reduction] = factor_rng.uniform(.7, .9, reduction.sum())
    values[positive] *= factors[positive]
    frame["valor_bruto"] = np.round(values, 2)
    if not np.isfinite(frame.valor_bruto).all() or (frame.valor_bruto <= 0).any():
        raise ValueError("Valor nao positivo no cenario")
    targets["fator_aplicado"] = factors
    targets["valor_legitimo_antes_injecao"] = np.round(legitimate_values, 2)
    targets["evento_legitimo"] = legitimate
    targets["regime_novo"] = regime.to_numpy()
    return frame, targets
