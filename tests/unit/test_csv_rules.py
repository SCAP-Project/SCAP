from datetime import date
from decimal import Decimal

import pandas as pd
import pytest

from etl.csv_pipeline.dimensions import stable_keys, sync_dimension
from etl.csv_pipeline.refined import build_balances
from etl.csv_pipeline.validation import validate_settlements


def test_parcelas_nao_podem_ultrapassar_valor_da_receita():
    transacoes = pd.DataFrame([dict(id_transacao_raw="T1", tipo_transacao="RECEITA",
                                   status_pagamento="PAGO", valor_liquido="100.01",
                                   data_transacao="2025-01-01")])
    recebimentos = pd.DataFrame([
        dict(id_recebimento_raw="R1", id_transacao_raw="T1", valor_recebido="100.01", data_recebimento="2025-01-01"),
        dict(id_recebimento_raw="R2", id_transacao_raw="T1", valor_recebido="50.00", data_recebimento="2025-02-01"),
    ])
    with pytest.raises(ValueError, match="conciliacao"):
        validate_settlements(transacoes, recebimentos, "recebimentos")
    recebimentos.loc[0, "valor_recebido"] = "50.01"
    validate_settlements(transacoes, recebimentos, "recebimentos")


def test_liquidacao_sem_transacao_falha():
    transacoes = pd.DataFrame([dict(id_transacao_raw="T1", tipo_transacao="RECEITA",
                                   status_pagamento="PAGO", valor_liquido="100.00", data_transacao="2025-01-01")])
    recebimentos = pd.DataFrame([dict(id_recebimento_raw="R1", id_transacao_raw="OUTRA",
                                      valor_recebido="100.00", data_recebimento="2025-01-01")])
    with pytest.raises(ValueError, match="transacao"):
        validate_settlements(transacoes, recebimentos, "recebimentos")


def test_scd_alteracao_no_mesmo_dia_e_em_dia_seguinte():
    incoming = pd.DataFrame([dict(id_area_natural="FIN", nome_area="Financeiro")])
    first = sync_dimension(incoming, None, "id_area_natural", "area_sk", date(2026, 11, 9))
    repeat = sync_dimension(incoming, first, "id_area_natural", "area_sk", date(2026, 11, 9))
    pd.testing.assert_frame_equal(first, repeat)
    incoming.loc[0, "nome_area"] = "Financas"
    same_day = sync_dimension(incoming, first, "id_area_natural", "area_sk", date(2026, 11, 9))
    assert len(same_day) == 1
    assert same_day.iloc[0].area_sk == first.iloc[0].area_sk
    next_day = sync_dimension(incoming, first, "id_area_natural", "area_sk", date(2026, 11, 10))
    assert len(next_day) == 2
    assert next_day.is_current.sum() == 1
    assert next_day.iloc[0].vigencia_fim == "2026-11-10"
    assert next_day.iloc[1].area_sk != next_day.iloc[0].area_sk


def test_scd_recusa_retroceder_data_de_observacao():
    incoming = pd.DataFrame([dict(id_area_natural="FIN", nome_area="Financeiro")])
    previous = sync_dimension(incoming, None, "id_area_natural", "area_sk", date(2026, 11, 10))
    incoming.loc[0, "nome_area"] = "Financas"
    with pytest.raises(ValueError, match="anterior"):
        sync_dimension(incoming, previous, "id_area_natural", "area_sk", date(2026, 11, 9))


def test_scd_recusa_reativacao_antes_do_fim_da_versao_fechada():
    original = pd.DataFrame([dict(id="A", nome="a"), dict(id="B", nome="b")])
    first = sync_dimension(original, None, "id", "sk", date(2026, 11, 1))
    removed = sync_dimension(original.iloc[1:], first, "id", "sk", date(2026, 11, 10))
    with pytest.raises(ValueError, match="anterior"):
        sync_dimension(original, removed, "id", "sk", date(2026, 11, 5))


def test_remocao_de_fato_falha_sem_reutilizar_chave():
    previous = pd.DataFrame([dict(id="A", sk=1), dict(id="B", sk=2)])
    with pytest.raises(ValueError, match="Remocao"):
        stable_keys(pd.DataFrame([dict(id="A")]), previous, "id", "sk")


def test_saldos_incluem_dia_sem_movimento_e_separam_area_moeda():
    transacoes = pd.DataFrame([
        dict(transacao_sk=1, area_sk=10, moeda_sk=1),
        dict(transacao_sk=2, area_sk=20, moeda_sk=2),
    ])
    pagamentos = pd.DataFrame([dict(transacao_sk=1, data="2025-01-03", moeda_sk=1, valor_pago="30.01")])
    recebimentos = pd.DataFrame([
        dict(transacao_sk=1, data="2025-01-01", moeda_sk=1, valor_recebido="100.01"),
        dict(transacao_sk=2, data="2025-01-03", moeda_sk=2, valor_recebido="7.00"),
    ])
    result = build_balances(transacoes, pagamentos, recebimentos)
    group = result[result.area_sk == 10].sort_values("data")
    assert list(group.data) == ["2025-01-01", "2025-01-02", "2025-01-03"]
    assert list(group.saldo_inicial.map(str)) == ["0.00", "100.01", "100.01"]
    assert list(group.saldo_final.map(str)) == ["100.01", "100.01", "70.00"]
    assert result[result.area_sk == 20].iloc[-1].saldo_final == Decimal("7.00")
    assert not result.duplicated(["data", "area_sk", "moeda_sk"]).any()


def test_saldos_vazios_tem_contrato_de_colunas():
    result = build_balances(pd.DataFrame(columns=["transacao_sk", "area_sk", "moeda_sk"]),
                            pd.DataFrame(), pd.DataFrame())
    assert result.empty
    assert "saldo_final" in result.columns
