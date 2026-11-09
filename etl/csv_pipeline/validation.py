"""Contratos e conciliacao financeira. Inconsistencias interrompem a carga."""

import pandas as pd

from .money import cents


def require(frame, columns, label):
    missing = set(columns) - set(frame.columns)
    if missing:
        raise ValueError(f"{label}: colunas ausentes: {sorted(missing)}")
    for column in columns:
        if frame[column].isna().any() or frame[column].astype(str).str.strip().eq("").any():
            raise ValueError(f"{label}: campo obrigatorio vazio: {column}")


def domain(frame, column, allowed):
    invalid = ~frame[column].isin(allowed)
    if invalid.any():
        raise ValueError(f"{column}: dominio invalido: {frame.loc[invalid, column].unique().tolist()}")


def iso_dates(series):
    dates = pd.to_datetime(series, format="%Y-%m-%d", errors="raise")
    return dates.dt.strftime("%Y-%m-%d")


def validate_settlements(transactions, settlements, entity):
    receipt = entity == "recebimentos"
    identifier = "id_recebimento_raw" if receipt else "id_pagamento_raw"
    value = "valor_recebido" if receipt else "valor_pago"
    day = "data_recebimento" if receipt else "data_pagamento"
    require(settlements, [identifier, "id_transacao_raw", value, day], entity)
    if settlements[identifier].duplicated().any():
        raise ValueError(f"{entity}: identificadores duplicados")
    joined = settlements.merge(transactions, on="id_transacao_raw", how="left", validate="many_to_one", indicator=True)
    if joined["_merge"].ne("both").any():
        raise ValueError(f"{entity}: transacao inexistente")
    expected_type = "RECEITA" if receipt else "DESPESA"
    if joined.tipo_transacao.ne(expected_type).any() or joined.status_pagamento.eq("CANCELADO").any():
        raise ValueError(f"{entity}: transacao cancelada ou de tipo incorreto")
    if (cents(joined[value]) <= 0).any():
        raise ValueError(f"{entity}: valor nao positivo")
    if (pd.to_datetime(joined[day]) < pd.to_datetime(joined.data_transacao)).any():
        raise ValueError(f"{entity}: liquidacao anterior a transacao")
    eligible = transactions[(transactions.tipo_transacao == expected_type) & transactions.status_pagamento.isin(["PAGO", "ATRASADO"])]
    if set(eligible.id_transacao_raw) != set(settlements.id_transacao_raw):
        raise ValueError(f"{entity}: cobertura incompleta de transacoes liquidadas")
    paid = joined[joined.status_pagamento == "PAGO"].copy()
    paid["centavos"] = cents(paid[value])
    actual = paid.groupby("id_transacao_raw").centavos.sum()
    expected = transactions.set_index("id_transacao_raw").valor_liquido
    if not actual.eq(cents(expected.loc[actual.index])).all():
        raise ValueError(f"{entity}: conciliacao divergente do valor liquido")


def validate_refined(tables):
    transactions = tables["fact_transacoes_financeiras"]
    for name, column in [("fact_pagamentos", "valor_pago"), ("fact_recebimentos", "valor_recebido")]:
        frame = tables[name]
        if not frame.transacao_sk.isin(transactions.transacao_sk).all():
            raise ValueError(f"{name}: transacao nao resolvida")
    balances = tables["fact_saldos_diarios"].sort_values(["area_sk", "moeda_sk", "data"])
    if balances.duplicated(["data", "area_sk", "moeda_sk"]).any():
        raise ValueError("Saldos diarios duplicados")
    if not cents(balances.saldo_final).eq(cents(balances.saldo_inicial) + cents(balances.entradas) - cents(balances.saidas)).all():
        raise ValueError("Identidade contabil divergente")
    previous = balances.groupby(["area_sk", "moeda_sk"]).saldo_final.shift().fillna(0)
    if not cents(balances.saldo_inicial).eq(cents(previous)).all():
        raise ValueError("Continuidade dos saldos divergente")
    for source, measure, total in [("fact_pagamentos", "valor_pago", "saidas"), ("fact_recebimentos", "valor_recebido", "entradas")]:
        if cents(tables[source][measure]).sum() != cents(balances[total]).sum():
            raise ValueError(f"Conciliacao de saldos divergente: {total}")
