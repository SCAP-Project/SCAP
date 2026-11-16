import numpy as np
import pandas as pd
import pytest

from ml.adaptive_features import ADAPTIVE_FEATURES, build_adaptive_features
from ml.improvement import calibrate
from ml.evaluation import compute_metrics


def fixture():
    return pd.DataFrame(
        dict(
            id_transacao_natural=["a", "b", "c", "d"],
            data=pd.to_datetime(
                ["2026-01-01", "2026-01-02", "2026-01-02", "2026-01-03"]
            ),
            id_parceiro_natural=["P"] * 4,
            valor_bruto=[100.0, 110.0, 1000.0, 120.0],
            tipo_transacao=["RECEITA"] * 4,
            id_area_natural=["A"] * 4,
            id_categoria_natural=["C"] * 4,
        )
    )


def test_current_day_excluded_and_future_mutation_invariant():
    source = fixture()
    first = build_adaptive_features(source).set_index("id_transacao_natural")
    assert first.loc["b", "n_20d"] == 1 and first.loc["c", "n_20d"] == 1
    changed = source.copy()
    changed.loc[changed.data >= "2026-01-02", "valor_bruto"] *= 100
    second = build_adaptive_features(changed).set_index("id_transacao_natural")
    assert first.loc["b", "std_20d"] == second.loc["b", "std_20d"]
    np.testing.assert_allclose(
        first.loc["a", ADAPTIVE_FEATURES].astype(float),
        second.loc["a", ADAPTIVE_FEATURES].astype(float),
    )


def test_day_window_excludes_old_events_and_finite_cold_start():
    source = fixture()
    source.loc[3, "data"] = pd.Timestamp("2026-03-01")
    features = build_adaptive_features(source).set_index("id_transacao_natural")
    assert features.loc["d", "n_20d"] == 0
    assert np.isfinite(features[ADAPTIVE_FEATURES]).all().all()
    assert features.loc["d", "z_20d"] == 0


def test_threshold_respects_recall_guardrail_and_ties():
    y = np.array([0] * 20 + [1] * 10)
    scores = np.array([0.1] * 20 + [0.2] * 5 + [0.8] * 5)
    threshold = calibrate(y, scores, min_recall=0.7)
    assert compute_metrics(y, scores, threshold)["recall"] >= 0.7
    assert threshold == 0.2
    with pytest.raises(ValueError):
        calibrate(np.zeros(30), scores)
