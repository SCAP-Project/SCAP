"""Gera pedidos e transações sintéticas antes da injeção de anomalias."""
import numpy as np
import pandas as pd

from .features import REQUIRED

DOCUMENT_COLUMNS = [
    "id_documento",
    "data_documento",
    "quantidade_documento",
    "preco_unitario_documento",
]
INPUT_COLUMNS = REQUIRED + DOCUMENT_COLUMNS
GENERATOR_CONFIG = dict(
    parceiros_recorrentes=100,
    parceiros_novos=20,
    probabilidade_anomalia=0.04,
    fracao_sutil=0.5,
    cobertura_documento=0.85,
    sigma_faturamento=0.045,
    sigma_documento=0.03,
    probabilidade_erro_documento=0.015,
    probabilidade_pico_legitimo=0.015,
    fracao_regime=0.15,
    fator_regime=1.6,
)


def generate_operations(context, seed, target_start, end, config=None):
    """Gera operações e documentos com ruídos independentes da adulteração posterior."""
    cfg = dict(GENERATOR_CONFIG, **(config or {}))
    operation_seed, document_seed, _ = np.random.SeedSequence(seed).spawn(3)
    rng = np.random.default_rng(operation_seed)
    documents = np.random.default_rng(document_seed)
    combinations = (
        context[["tipo_transacao", "id_area_natural", "id_categoria_natural"]]
        .drop_duplicates()
        .sort_values(["tipo_transacao", "id_area_natural", "id_categoria_natural"])
        .reset_index(drop=True)
    )
    n_old, n_new = cfg["parceiros_recorrentes"], cfg["parceiros_novos"]
    shifted = set(rng.choice(n_old, round(n_old * cfg["fracao_regime"]), replace=False))
    dates = pd.bdate_range("2026-01-01", end)
    start = pd.Timestamp(target_start)
    rows = []
    diagnostics = []
    for partner_index in range(n_old + n_new):
        partner = f"CTX{seed}-P{partner_index:03d}"
        base_price = np.clip(rng.lognormal(np.log(400), 0.8), 25, 15000)
        daily_probability = rng.uniform(0.40, 0.85)
        typical_quantity = rng.uniform(2, 12)
        drift = rng.uniform(-0.0004, 0.0006)
        ctx = combinations.iloc[rng.integers(len(combinations))].to_dict()
        for day in dates:
            if partner_index >= n_old and day < start:
                continue
            if rng.random() >= daily_probability:
                continue
            regime = partner_index in shifted and day >= start
            peak = rng.random() < cfg["probabilidade_pico_legitimo"]
            quantity = max(1, int(rng.poisson(typical_quantity)))
            if peak:
                quantity *= int(rng.integers(2, 5))
            if regime:
                quantity = max(1, round(quantity * cfg["fator_regime"]))
            unit_price = (
                base_price
                * np.exp(drift * (day - pd.Timestamp("2026-01-01")).days)
                * rng.lognormal(0, 0.025)
            )
            # O pedido é uma medição anterior, independente da adulteração.
            document_day = day - pd.Timedelta(days=int(documents.integers(1, 6)))
            document_price = round(
                unit_price * documents.lognormal(0, cfg["sigma_documento"]), 2
            )
            fault = documents.random() < cfg["probabilidade_erro_documento"]
            if fault:
                document_price = round(document_price * documents.uniform(0.6, 1.6), 2)
            present = documents.random() < cfg["cobertura_documento"]
            commercial_value = (
                quantity * unit_price * rng.lognormal(0, cfg["sigma_faturamento"])
            )
            identifier = f"CTX{seed}-T{len(rows)+1:06d}"
            rows.append(
                dict(
                    id_transacao_natural=identifier,
                    data=day,
                    id_parceiro_natural=partner,
                    valor_bruto=round(commercial_value, 2),
                    **ctx,
                    id_documento=f"PED{seed}-{len(rows)+1:06d}" if present else None,
                    data_documento=document_day if present else pd.NaT,
                    quantidade_documento=quantity if present else np.nan,
                    preco_unitario_documento=document_price if present else np.nan,
                )
            )
            diagnostics.append(
                dict(
                    id_transacao_natural=identifier,
                    pico_legitimo=peak,
                    regime_novo=regime,
                    erro_documento=fault,
                    parceiro_novo=partner_index >= n_old,
                )
            )
    return pd.DataFrame(rows)[INPUT_COLUMNS], pd.DataFrame(diagnostics)


def inject_alterations(operations, seed, probability=0.04, subtle_fraction=0.5):
    """Segunda etapa causal: altera somente valor_bruto, mantém o documento.

    O gabarito retorna separado. Nenhuma informação desta função compõe o
    documento ou os atributos usados para inferência.
    """
    corruption_seed = np.random.SeedSequence(seed).spawn(3)[2]
    rng = np.random.default_rng(corruption_seed)
    frame = operations.copy()
    labels = []
    for index, row in frame.iterrows():
        anomaly = rng.random() < probability
        factor = 1.0
        mechanism = "normal"
        if anomaly:
            subtle = rng.random() < subtle_fraction
            inflation = rng.random() < 0.7
            factor = (
                rng.uniform(1.1, 1.3)
                if subtle and inflation
                else (
                    rng.uniform(0.7, 0.9)
                    if subtle
                    else (
                        rng.uniform(1.5, 2.5) if inflation else rng.uniform(0.35, 0.65)
                    )
                )
            )
            mechanism = ("sutil_" if subtle else "ampla_") + (
                "inflacao" if inflation else "reducao"
            )
        labels.append(
            dict(
                id_transacao_natural=row.id_transacao_natural,
                flag_anomalia=anomaly,
                mecanismo=mechanism,
                fator_aplicado=factor,
                valor_antes_injecao=row.valor_bruto,
            )
        )
        frame.at[index, "valor_bruto"] = round(row.valor_bruto * factor, 2)
    return frame, pd.DataFrame(labels)


def generate_context_client(context, seed, target_start, end):
    operations, diagnostics = generate_operations(context, seed, target_start, end)
    source, labels = inject_alterations(
        operations,
        seed,
        GENERATOR_CONFIG["probabilidade_anomalia"],
        GENERATOR_CONFIG["fracao_sutil"],
    )
    target = labels.merge(diagnostics, on="id_transacao_natural", validate="one_to_one")
    source = source.sort_values(["data", "id_transacao_natural"]).reset_index(drop=True)
    target = (
        target.set_index("id_transacao_natural")
        .loc[source.id_transacao_natural]
        .reset_index()
    )
    return source, target


def validate_context_input(frame):
    if set(frame.columns) != set(INPUT_COLUMNS):
        raise ValueError("Entrada deve conter somente os onze campos do contrato")
    frame = frame[INPUT_COLUMNS].copy()
    frame["data"] = pd.to_datetime(frame.data, errors="raise")
    frame["data_documento"] = pd.to_datetime(frame.data_documento, errors="raise")
    for c in ["valor_bruto", "quantidade_documento", "preco_unitario_documento"]:
        frame[c] = pd.to_numeric(frame[c], errors="raise")
    if (
        frame.empty
        or frame[REQUIRED].isna().any().any()
        or frame.id_transacao_natural.duplicated().any()
    ):
        raise ValueError("Entrada vazia, incompleta ou duplicada")
    if not frame.tipo_transacao.isin(["RECEITA", "DESPESA"]).all():
        raise ValueError("Tipo inválido")
    for c in REQUIRED:
        if c not in ["data", "valor_bruto"]:
            if frame[c].astype(str).str.strip().eq("").any():
                raise ValueError("Identificador vazio")
    if not frame.data.eq(frame.data.dt.normalize()).all():
        raise ValueError("Data deve ser diária")
    if not np.isfinite(frame.valor_bruto).all() or (frame.valor_bruto <= 0).any():
        raise ValueError("Valor inválido")
    missing = frame[DOCUMENT_COLUMNS].isna()
    if not (missing.all(axis=1) | ~missing.any(axis=1)).all():
        raise ValueError("Documento parcialmente preenchido")
    present = ~missing.all(axis=1)
    if (frame.loc[present, "data_documento"] >= frame.loc[present, "data"]).any():
        raise ValueError("Documento deve ser anterior à transação")
    for c in ["quantidade_documento", "preco_unitario_documento"]:
        values = frame.loc[present, c]
        if not np.isfinite(values).all() or (values <= 0).any():
            raise ValueError("Quantidade/preço inválido")
    if frame.loc[present, "id_documento"].duplicated().any():
        raise ValueError("Documento duplicado no contrato de uma linha por pedido")
    return frame


def degrade_documents(frame, seed, mode):
    """Desafio pareado: altera a medição documental, mantendo transações/alvos."""
    result = frame.copy()
    rng = np.random.default_rng(seed + 900000)
    if mode == "sem_documentos":
        result.loc[:, DOCUMENT_COLUMNS] = [None, pd.NaT, np.nan, np.nan]
    elif mode == "documentos_degradados":
        missing = rng.random(len(result)) < 0.40
        result.loc[missing, DOCUMENT_COLUMNS] = [None, pd.NaT, np.nan, np.nan]
        fault = (
            rng.random(len(result)) < 0.20
        ) & result.id_documento.notna().to_numpy()
        result.loc[fault, "preco_unitario_documento"] *= rng.uniform(
            0.65, 1.5, fault.sum()
        )
        present = result.id_documento.notna()
        result.loc[present, "preco_unitario_documento"] *= rng.lognormal(
            0, 0.08, present.sum()
        )
    else:
        raise ValueError("Cenário desconhecido")
    return validate_context_input(result)
