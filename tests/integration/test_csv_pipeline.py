from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from etl.csv_pipeline.pipeline import run_pipeline


def write_fixture(data):
    raw = {
        "areas": [dict(codigo_area="FIN", nome_area="Financeiro")],
        "categorias_contabeis": [dict(id_categoria_raw="1", nome_categoria="Venda", tipo_categoria="RECEITA", codigo_contabil="4.1"),
                                 dict(id_categoria_raw="2", nome_categoria="Compra", tipo_categoria="DESPESA", codigo_contabil="2.1")],
        "fornecedores_clientes": [dict(id_fornecedor_raw="P1", nome_fornecedor="Parceiro", tipo_fornecedor="AMBOS", rating_credito="AAA", prazo_medio="2")],
        "funcionarios": [dict(id_funcionario_raw="1", nome="Pessoa", cpf="123", cargo="Analista", departamento="FIN",
                              data_admissao="2024-01-01", tipo_contrato="CLT", salario="2000.00")],
        "transacoes_financeiras": [dict(id_transacao_raw="T1", tipo_transacao="RECEITA", id_categoria_raw="1", valor_bruto="100.01", valor_liquido="100.01"),
                                   dict(id_transacao_raw="T2", tipo_transacao="DESPESA", id_categoria_raw="2", valor_bruto="30.01", valor_liquido="30.01")],
        "pagamentos": [dict(id_pagamento_raw="1", id_transacao_raw="T2", data_pagamento="2025-01-03", valor_pago="30.01", metodo_pagamento="PIX")],
        "recebimentos": [dict(id_recebimento_raw="1", id_transacao_raw="T1", data_recebimento="2025-01-01", valor_recebido="50.01", metodo_recebimento="PIX"),
                         dict(id_recebimento_raw="2", id_transacao_raw="T1", data_recebimento="2025-01-03", valor_recebido="50.00", metodo_recebimento="PIX")],
    }
    for transaction in raw["transacoes_financeiras"]:
        transaction.update(data_transacao="2025-01-01", data_competencia="2025-01-01", codigo_area_raw="FIN", id_fornecedor_raw="P1",
                           moeda="BRL", forma_pagamento="PIX", status_pagamento="PAGO", descricao="  Venda   teste  ")
    for entity, rows in raw.items():
        folder = data / "raw" / entity
        folder.mkdir(parents=True)
        frame = pd.DataFrame(rows)
        frame["source_system"] = "TESTE"
        frame.to_csv(folder / "fixture.csv", index=False)


def test_fluxo_csv_completo_reexecucao_e_historico(tmp_path):
    write_fixture(tmp_path)
    result = run_pipeline(tmp_path, observed_on=date(2026, 11, 9))
    assert result["counts"]["refined.fact_recebimentos"] == 2
    assert result["counts"]["refined.fact_saldos_diarios"] == 3
    outputs = {str(p.relative_to(tmp_path)): p.read_bytes() for layer in ["trusted", "refined"] for p in (tmp_path / layer).glob("*.csv")}
    run_pipeline(tmp_path, observed_on=date(2026, 11, 9))
    assert all((tmp_path / p).read_bytes() == content for p, content in outputs.items())
    path = tmp_path / "raw/areas/fixture.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "nome_area"] = "Financas"
    frame.to_csv(path, index=False)
    run_pipeline(tmp_path, observed_on=date(2026, 11, 10))
    areas = pd.read_csv(tmp_path / "refined/dim_area.csv")
    facts = pd.read_csv(tmp_path / "refined/fact_transacoes_financeiras.csv")
    assert len(areas) == 2
    assert areas.is_current.sum() == 1
    assert set(facts.area_sk) == {1}  # nao reatribuir transacoes antigas a versao nova
    assert (tmp_path / "exports/etl_manifest.json").is_file()


def test_erro_na_conciliacao_nao_substitui_saidas_validas(tmp_path):
    write_fixture(tmp_path)
    run_pipeline(tmp_path)
    target = tmp_path / "refined/fact_recebimentos.csv"
    before = target.read_bytes()
    raw = tmp_path / "raw/recebimentos/fixture.csv"
    frame = pd.read_csv(raw, dtype=str)
    frame.loc[0, "valor_recebido"] = "100.01"
    frame.to_csv(raw, index=False)
    with pytest.raises(ValueError, match="conciliacao"):
        run_pipeline(tmp_path)
    assert target.read_bytes() == before


def test_falta_de_arquivo_obrigatorio_interrompe_fluxo(tmp_path):
    write_fixture(tmp_path)
    (tmp_path / "raw/pagamentos/fixture.csv").unlink()
    with pytest.raises(FileNotFoundError, match="pagamentos"):
        run_pipeline(tmp_path)


def test_falha_de_gravacao_restaura_geracao_anterior(tmp_path, monkeypatch):
    import os
    write_fixture(tmp_path)
    run_pipeline(tmp_path, observed_on=date(2026, 11, 9))
    before = {p: p.read_bytes() for layer in ["trusted", "refined", "exports"] for p in (tmp_path / layer).glob("*") if p.is_file()}
    area = tmp_path / "raw/areas/fixture.csv"
    frame = pd.read_csv(area)
    frame.loc[0, "nome_area"] = "Financas"
    frame.to_csv(area, index=False)
    original = os.replace
    calls = 0

    def fail_second(source, target):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("falha simulada")
        return original(source, target)

    monkeypatch.setattr(os, "replace", fail_second)
    with pytest.raises(OSError, match="falha simulada"):
        run_pipeline(tmp_path, observed_on=date(2026, 11, 10))
    assert all(p.read_bytes() == contents for p, contents in before.items())


def test_manifesto_impede_retroceder_apos_execucao_sem_mudancas(tmp_path):
    write_fixture(tmp_path)
    run_pipeline(tmp_path, observed_on=date(2026, 11, 1))
    run_pipeline(tmp_path, observed_on=date(2026, 11, 10))
    with pytest.raises(ValueError, match="anterior"):
        run_pipeline(tmp_path, observed_on=date(2026, 11, 5))
