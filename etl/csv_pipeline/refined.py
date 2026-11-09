"""Modelo dimensional e saldos diarios para analise local."""

import pandas as pd

from .money import amounts, cents


BALANCE_COLUMNS = ["saldo_sk", "data", "tempo_sk", "area_sk", "moeda_sk", "saldo_inicial", "saldo_final", "entradas", "saidas"]


def build_balances(transactions, payments, receipts):
    movements = []
    for frame, value, target in [(payments, "valor_pago", "saidas"), (receipts, "valor_recebido", "entradas")]:
        if frame.empty:
            continue
        rows = frame[["transacao_sk", "data", "moeda_sk", value]].merge(
            transactions[["transacao_sk", "area_sk"]], on="transacao_sk", how="left", validate="many_to_one")
        if rows.area_sk.isna().any():
            raise ValueError("Saldo: transacao nao resolvida")
        rows["entradas"] = 0
        rows["saidas"] = 0
        rows[target] = cents(rows[value])
        movements.append(rows[["data", "area_sk", "moeda_sk", "entradas", "saidas"]])
    if not movements:
        return pd.DataFrame(columns=BALANCE_COLUMNS)
    moves = pd.concat(movements, ignore_index=True)
    moves["data"] = pd.to_datetime(moves["data"])
    groups = ["area_sk", "moeda_sk"]
    daily = moves.groupby(["data"] + groups, as_index=False)[["entradas", "saidas"]].sum()
    dates = pd.DataFrame({"data": pd.date_range(moves.data.min(), moves.data.max())})
    spine = moves[groups].drop_duplicates().merge(dates, how="cross")
    result = spine.merge(daily, on=["data"] + groups, how="left").fillna({"entradas": 0, "saidas": 0})
    result = result.sort_values(groups + ["data"]).reset_index(drop=True)
    result[["entradas", "saidas"]] = result[["entradas", "saidas"]].astype("int64")
    result["movimento"] = result.entradas - result.saidas
    result["saldo_final"] = result.groupby(groups).movimento.cumsum()
    result["saldo_inicial"] = result.saldo_final - result.movimento
    for column in ["entradas", "saidas", "saldo_inicial", "saldo_final"]:
        result[column] = amounts(result[column])
    result["tempo_sk"] = result.data.dt.strftime("%Y%m%d").astype(int)
    result["data"] = result.data.dt.strftime("%Y-%m-%d")
    result["saldo_sk"] = range(1, len(result) + 1)
    return result[BALANCE_COLUMNS]


def build_refined(trusted):
    names = {"areas": "dim_area", "categorias_contabeis": "dim_categoria_contabil",
             "fornecedores_clientes": "dim_fornecedor_cliente", "funcionarios": "dim_funcionario", "moedas": "dim_moeda"}
    result = {target: trusted[source].copy() for source, target in names.items()}
    result["dim_fornecedor_cliente"] = result["dim_fornecedor_cliente"].rename(columns={"nome_fornecedor": "nome_parceiro", "tipo_fornecedor": "tipo_parceiro"})
    transactions = trusted["transacoes_financeiras"].copy()
    transactions["tempo_sk"] = transactions.data_transacao.str.replace("-", "").astype(int)
    transactions = transactions.rename(columns={"data_transacao": "data"})
    result["fact_transacoes_financeiras"] = transactions
    for entity, natural, surrogate, day in [
        ("pagamentos", "id_pagamento_natural", "pagamento_sk", "data_pagamento"),
        ("recebimentos", "id_recebimento_natural", "recebimento_sk", "data_recebimento"),
    ]:
        frame = trusted[entity].copy()
        frame = frame.merge(transactions[["transacao_sk", "parceiro_sk"]], on="transacao_sk", how="left", validate="many_to_one")
        if frame.parceiro_sk.isna().any():
            raise ValueError(f"{entity}: parceiro nao resolvido")
        frame["tempo_sk"] = frame[day].str.replace("-", "").astype(int)
        result["fact_" + entity] = frame.rename(columns={day: "data"})
    result["fact_saldos_diarios"] = build_balances(transactions, result["fact_pagamentos"], result["fact_recebimentos"])
    all_dates = pd.concat([transactions.data, result["fact_pagamentos"].data, result["fact_recebimentos"].data])
    start = min("2023-01-01", all_dates.min())
    end = max("2026-12-31", all_dates.max())
    dates = pd.Series(pd.date_range(start, end))
    months = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    weekdays = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    result["dim_tempo"] = pd.DataFrame({
        "tempo_sk": dates.dt.strftime("%Y%m%d").astype(int), "data": dates.dt.strftime("%Y-%m-%d"),
        "ano": dates.dt.year, "semestre": (dates.dt.month - 1) // 6 + 1,
        "trimestre": dates.dt.quarter, "mes": dates.dt.month, "dia": dates.dt.day,
        "nome_mes": dates.dt.month.map(lambda m: months[m - 1]), "dia_semana": dates.dt.dayofweek + 1,
        "nome_dia_semana": dates.dt.dayofweek.map(lambda d: weekdays[d]),
        "semana_ano": dates.dt.isocalendar().week.to_numpy(), "eh_dia_util": dates.dt.dayofweek < 5,
        "eh_feriado": False,
    })
    return result
