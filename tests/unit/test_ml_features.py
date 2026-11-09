import numpy as np
import pandas as pd
import pytest

from ml.features import build_features, MODEL_FEATURES
from ml.split import assign_periods
from ml.evaluation import choose_threshold


def transactions():
    return pd.DataFrame([
        dict(id_transacao_natural="A", data="2024-01-01", id_parceiro_natural="P1", tipo_transacao="RECEITA", id_area_natural="FIN", id_categoria_natural="1", valor_bruto=100.0),
        dict(id_transacao_natural="B", data="2024-01-02", id_parceiro_natural="P1", tipo_transacao="RECEITA", id_area_natural="FIN", id_categoria_natural="1", valor_bruto=200.0),
        dict(id_transacao_natural="C", data="2024-01-02", id_parceiro_natural="P1", tipo_transacao="RECEITA", id_area_natural="FIN", id_categoria_natural="1", valor_bruto=300.0),
        dict(id_transacao_natural="D", data="2024-01-03", id_parceiro_natural="P1", tipo_transacao="RECEITA", id_area_natural="FIN", id_categoria_natural="1", valor_bruto=400.0),
    ])


def test_historico_exclui_transacao_atual_e_todo_o_mesmo_dia():
    features = build_features(transactions()).set_index("id_transacao_natural")
    assert features.loc["A", "qtd_historico"] == 0
    assert features.loc["B", "qtd_historico"] == 1
    assert features.loc["C", "qtd_historico"] == 1
    assert features.loc["D", "qtd_historico"] == 3
    assert features.loc["B", "media_log_historico"] == pytest.approx(np.log1p(100))
    assert features.loc["D", "media_log_historico"] == pytest.approx(np.log1p([100, 200, 300]).mean())


def test_futuro_e_colunas_de_gabarito_nao_alteram_atributos_passados():
    source = transactions()
    original = build_features(source.iloc[:3])
    source["flag_anomalia"] = True
    source["status_pagamento"] = "ATRASADO"
    source["rating_credito"] = "C"
    source["fator_aplicado"] = 3.5
    appended = build_features(source).iloc[:3].reset_index(drop=True)
    pd.testing.assert_frame_equal(original.reset_index(drop=True), appended)
    assert not {"flag_anomalia", "status_pagamento", "rating_credito", "fator_aplicado"}.intersection(MODEL_FEATURES)


def test_periodos_nao_se_sobrepoem_e_nao_ignoram_datas():
    source = pd.DataFrame({"data": ["2024-12-31", "2025-01-01", "2025-06-30", "2025-07-01"]})
    assert assign_periods(source).tolist() == ["treino", "validacao", "validacao", "teste"]
    with pytest.raises(ValueError, match="fora"):
        assign_periods(pd.DataFrame({"data": ["2026-01-01"]}))


def test_janela_90_dias_descarta_observacoes_antigas_e_separa_tipo():
    source = transactions()
    source["data"] = ["2024-01-01", "2024-03-31", "2024-04-01", "2024-04-02"]
    source.loc[2, "tipo_transacao"] = "DESPESA"
    result = build_features(source).set_index("id_transacao_natural")
    assert result.loc["B", "qtd_90d"] == 1  # 90 dias exatos, limite esquerdo incluido
    assert result.loc["C", "qtd_historico"] == 0  # outro tipo de transacao
    assert result.loc["D", "qtd_historico"] == 2
    assert result.loc["D", "qtd_90d"] == 1  # janeiro saiu da janela


def test_limiar_trata_empates_e_usa_score_maior_como_anomalia():
    y = np.array([0, 0, 1, 1])
    score = np.array([0.1, 0.2, 0.8, 0.9])
    threshold = choose_threshold(y, score)
    assert threshold == pytest.approx(0.8)
    assert np.array_equal(score >= threshold, y.astype(bool))
