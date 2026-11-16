import numpy as np
import pandas as pd
import pytest

from ml.context_data import (
    DOCUMENT_COLUMNS,
    generate_operations,
    inject_alterations,
    validate_context_input,
    degrade_documents,
)
from ml.context_model import build_context_features, CONTEXT_FEATURES, predict_context


def context():
    return pd.DataFrame(
        dict(
            tipo_transacao=["RECEITA"],
            id_area_natural=["A"],
            id_categoria_natural=["C"],
        )
    )


def test_document_generated_before_target_and_unchanged_by_injection():
    operations, _ = generate_operations(
        context(),
        31,
        "2026-01-10",
        "2026-01-20",
        dict(parceiros_recorrentes=2, parceiros_novos=1),
    )
    clean, y0 = inject_alterations(operations, 31, probability=0)
    altered, y1 = inject_alterations(operations, 31, probability=1)
    pd.testing.assert_frame_equal(clean[DOCUMENT_COLUMNS], altered[DOCUMENT_COLUMNS])
    assert not y0.flag_anomalia.any() and y1.flag_anomalia.all()
    assert (clean.valor_bruto != altered.valor_bruto).all()
    validate_context_input(altered)


def test_label_and_future_document_rejected():
    operations, _ = generate_operations(
        context(),
        32,
        "2026-01-10",
        "2026-01-20",
        dict(parceiros_recorrentes=2, parceiros_novos=1),
    )
    leaked = operations.assign(flag_anomalia=False)
    with pytest.raises(ValueError):
        build_context_features(leaked)
    available = operations.id_documento.notna()
    index = operations[available].index[0]
    future = operations.copy()
    future.loc[index, "data_documento"] = future.loc[index, "data"] + pd.Timedelta(
        days=1
    )
    with pytest.raises(ValueError):
        build_context_features(future)


def test_future_mutation_does_not_change_earlier_features():
    operations, _ = generate_operations(
        context(),
        33,
        "2026-01-10",
        "2026-01-20",
        dict(parceiros_recorrentes=2, parceiros_novos=1),
    )
    first = build_context_features(operations).set_index("id_transacao_natural")
    changed = operations.copy()
    changed.loc[changed.data >= "2026-01-15", "valor_bruto"] *= 10
    second = build_context_features(changed).set_index("id_transacao_natural")
    ids = first[first.data < "2026-01-15"].index
    np.testing.assert_allclose(
        first.loc[ids, CONTEXT_FEATURES], second.loc[ids, CONTEXT_FEATURES]
    )


def test_missing_context_and_degradation_preserve_values():
    operations, _ = generate_operations(
        context(),
        34,
        "2026-01-10",
        "2026-01-20",
        dict(parceiros_recorrentes=2, parceiros_novos=1),
    )
    missing = degrade_documents(operations, 34, "sem_documentos")
    features = build_context_features(missing)
    assert features.sem_documento.eq(1).all()
    assert features.abs_log_razao_documento.eq(0).all()
    np.testing.assert_equal(
        operations.valor_bruto.to_numpy(), missing.valor_bruto.to_numpy()
    )
    bundle = dict(kind="document_rule")
    history = missing[missing.data < "2026-01-15"]
    batch = missing[missing.data >= "2026-01-15"]
    output = predict_context(history, batch, bundle, 0.1)
    assert not output.alerta.any() and not output.documento_disponivel.any()
