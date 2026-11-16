import numpy as np
import pandas as pd
import pytest

from ml.client_demo import CONFIG, generate_client_data, predict_frames, read_input


def context():
    return pd.DataFrame(
        {
            "tipo_transacao": ["RECEITA", "DESPESA"],
            "id_area_natural": ["FIN", "OP"],
            "id_categoria_natural": ["1", "2"],
        }
    )


def test_dummy_reproduzivel_rotulos_separados_e_periodos_disjuntos():
    history, batch, labels = generate_client_data(context())
    second = generate_client_data(context())
    for first, repeated in zip([history, batch, labels], second):
        pd.testing.assert_frame_equal(first, repeated)
    assert history.data.max() < batch.data.min()
    assert not set(history.id_transacao_natural) & set(batch.id_transacao_natural)
    assert "flag_anomalia" not in history and "flag_anomalia" not in batch
    normal_peaks = labels[labels.pico_legitimo]
    assert len(normal_peaks) and not normal_peaks.flag_anomalia.any()
    assert set(labels.id_transacao_natural) == set(
        pd.concat([history, batch]).id_transacao_natural
    )
    assert (
        len(set(batch.id_parceiro_natural) - set(history.id_parceiro_natural))
        == CONFIG["parceiros_novos"]
    )


def test_contrato_recusa_gabarito_no_upload(tmp_path):
    _, batch, _ = generate_client_data(context())
    path = tmp_path / "upload.csv"
    batch.assign(flag_anomalia=False).to_csv(path, index=False)
    with pytest.raises(ValueError, match="sete campos"):
        read_input(path)
    batch.to_csv(path, index=False)
    assert len(read_input(path)) == len(batch)
    invalid = batch.copy()
    invalid.iloc[0, invalid.columns.get_loc("valor_bruto")] = np.inf
    invalid.to_csv(path, index=False)
    with pytest.raises(ValueError, match="inválidos"):
        read_input(path)


def test_inferencia_respeita_futuro_e_explica_abstinencia():
    history, batch, _ = generate_client_data(context())
    bundle = {"kind": "historical"}
    predicted = predict_frames(history, batch, bundle, 1.68)
    changed = batch.copy()
    cutoff = batch.data.min() + pd.Timedelta(days=10)
    changed.loc[changed.data > cutoff, "valor_bruto"] *= 50
    again = predict_frames(history, changed, bundle, 1.68)
    pd.testing.assert_frame_equal(
        predicted[predicted.data <= cutoff], again[again.data <= cutoff]
    )
    abstained = predicted[~predicted.contexto_suficiente]
    assert len(abstained) > 0
    assert abstained.situacao.eq("CONTEXTO_INSUFICIENTE").all()
    assert not abstained.alerta.any()
    bad_history = pd.concat([history, batch.iloc[:1]])
    with pytest.raises(ValueError, match="anterior"):
        predict_frames(bad_history, batch, bundle, 1.68)
