import numpy as np
import pandas as pd
import pytest

from ml.robustness.scenarios import apply_scenario
from ml.robustness.ablations import FEATURE_GROUPS
from ml.robustness.audit import manual_history_check
from ml.features import build_features
from ml.robustness.run import assert_protocol_matches


def fixture():
    base = pd.DataFrame({
        "id_transacao_natural": [f"T{i}" for i in range(200)],
        "data": pd.date_range("2024-01-01", periods=200, freq="3D"),
        "id_parceiro_natural": [f"P{i % 10}" for i in range(200)],
        "tipo_transacao": "RECEITA", "id_area_natural": "FIN", "id_categoria_natural": "1",
        "valor_bruto": 100.0,
    })
    labels = pd.DataFrame({"id_transacao_natural": base.id_transacao_natural,
                           "flag_anomalia": np.arange(200) % 10 == 0,
                           "fator_aplicado": np.where(np.arange(200) % 10 == 0, 2.0, np.nan)})
    return base, labels


def test_cenario_original_preserva_mecanismo_e_gabarito():
    base, labels = fixture()
    frame, target = apply_scenario(base, labels, "original", 101)
    assert set(frame.columns) == set(base.columns)
    assert frame.loc[0, "valor_bruto"] == 200
    assert frame.loc[1, "valor_bruto"] == 100
    assert target.flag_anomalia.tolist() == labels.flag_anomalia.tolist()


def test_sutileza_muda_intensidade_sem_criar_rotulo_nas_features():
    base, labels = fixture()
    first, target = apply_scenario(base, labels, "sutis", 101)
    second, _ = apply_scenario(base, labels, "sutis", 101)
    pd.testing.assert_frame_equal(first, second)
    assert target.loc[target.flag_anomalia, "fator_aplicado"].between(1.1, 1.3).all()
    assert "flag_anomalia" not in first and "evento_legitimo" not in first
    assert target.flag_anomalia.sum() == labels.flag_anomalia.sum()


def test_eventos_legitimos_continuam_normais_e_mudanca_afeta_normais():
    base, labels = fixture()
    frame, target = apply_scenario(base, labels, "extremos_legitimos", 101)
    legit = target.evento_legitimo
    assert legit.any()
    assert not target.loc[legit, "flag_anomalia"].any()
    assert (frame.loc[legit, "valor_bruto"] > base.loc[legit, "valor_bruto"]).all()


def test_ablacao_sem_valor_remove_tambem_todos_os_derivados_do_valor_atual():
    columns = FEATURE_GROUPS["sem_valor_atual"][0]
    assert not set(columns) & {"log_valor", "z_historico", "z_90d", "desvio_log_historico", "desvio_log_90d"}


def test_auditoria_independente_detecta_historico_adulterado():
    base, _ = fixture()
    features = build_features(base)
    assert manual_history_check(base, features, sample_size=20)["aprovado"]
    features["media_log_historico"] = 999
    assert not manual_history_check(base, features, sample_size=200)["aprovado"]


def test_gabarito_fora_de_ordem_e_alinhado_por_id():
    base, labels = fixture()
    original, targets = apply_scenario(base, labels, "original", 101)
    shuffled, shuffled_targets = apply_scenario(base, labels.sample(frac=1, random_state=42), "original", 101)
    pd.testing.assert_frame_equal(original, shuffled)
    pd.testing.assert_frame_equal(targets, shuffled_targets)


def test_registro_recusa_codigo_ou_ambiente_diferente():
    import copy
    registered = dict(originais_sha256={"modelo": "abc"}, configuracao={"seed": 101},
                      metodos_sha256={"scenarios.py": "123"}, versoes={"numpy": "1.26.2"})
    assert_protocol_matches(registered, copy.deepcopy(registered))
    for key in ["originais_sha256", "configuracao", "metodos_sha256", "versoes"]:
        changed = copy.deepcopy(registered)
        changed[key] = {"alterado": "sim"}
        with pytest.raises(ValueError, match="mudou"):
            assert_protocol_matches(registered, changed)
