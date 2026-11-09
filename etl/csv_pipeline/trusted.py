"""Padronizacao, integridade referencial e historico da camada trusted CSV."""

from datetime import date

import pandas as pd

from .dimensions import resolve_fk, stable_keys, sync_dimension
from .money import amounts, cents
from .validation import domain, iso_dates, require, validate_settlements


REQUIRED = {
    "areas": ["codigo_area", "nome_area"],
    "categorias_contabeis": ["id_categoria_raw", "nome_categoria", "tipo_categoria", "codigo_contabil"],
    "fornecedores_clientes": ["id_fornecedor_raw", "nome_fornecedor", "tipo_fornecedor"],
    "funcionarios": ["id_funcionario_raw", "nome", "cpf", "cargo", "departamento", "data_admissao", "tipo_contrato", "salario"],
    "transacoes_financeiras": ["id_transacao_raw", "data_transacao", "data_competencia", "codigo_area_raw", "id_fornecedor_raw", "id_categoria_raw", "moeda", "valor_bruto", "valor_liquido", "tipo_transacao", "forma_pagamento", "status_pagamento", "descricao"],
    "pagamentos": ["id_pagamento_raw", "id_transacao_raw", "data_pagamento", "valor_pago", "metodo_pagamento"],
    "recebimentos": ["id_recebimento_raw", "id_transacao_raw", "data_recebimento", "valor_recebido", "metodo_recebimento"],
}

IDENTIFIERS = {name: columns[0] for name, columns in REQUIRED.items()}
METHODS = ["PIX", "BOLETO", "TED", "TRANSFERENCIA", "CARTAO"]


def normalize_raw(raw):
    normalized = {}
    for entity, columns in REQUIRED.items():
        frame = raw[entity].copy().fillna("")
        if frame.empty:
            raise ValueError(f"{entity}: arquivo vazio")
        require(frame, columns + ["source_system"], entity)
        for column in frame.select_dtypes(include=["object", "string"]):
            frame[column] = frame[column].map(lambda value: value.strip() if isinstance(value, str) else value)
        require(frame, columns, entity)
        if frame[IDENTIFIERS[entity]].duplicated().any():
            raise ValueError(f"{entity}: chave duplicada")
        for column in [c for c in frame if c.startswith("valor_") or c == "salario"]:
            values = cents(frame[column])
            if (values <= 0).any():
                raise ValueError(f"{entity}: {column} nao positivo")
            frame[column] = amounts(values)
        for column in [c for c in frame if c.startswith("data_")]:
            frame[column] = iso_dates(frame[column])
        normalized[entity] = frame
    domain(normalized["categorias_contabeis"], "tipo_categoria", ["RECEITA", "DESPESA"])
    domain(normalized["fornecedores_clientes"], "tipo_fornecedor", ["CLIENTE", "FORNECEDOR", "AMBOS"])
    domain(normalized["funcionarios"], "tipo_contrato", ["CLT", "PJ", "ESTAGIO", "TEMPORARIO"])
    transactions = normalized["transacoes_financeiras"]
    domain(transactions, "tipo_transacao", ["RECEITA", "DESPESA"])
    domain(transactions, "status_pagamento", ["PAGO", "ATRASADO", "CANCELADO"])
    domain(transactions, "forma_pagamento", METHODS)
    domain(transactions, "moeda", ["BRL", "USD", "EUR"])
    if (cents(transactions.valor_liquido) > cents(transactions.valor_bruto)).any():
        raise ValueError("Valor liquido maior que bruto")
    categories = normalized["categorias_contabeis"].set_index("id_categoria_raw").tipo_categoria
    if not transactions.id_categoria_raw.map(categories).eq(transactions.tipo_transacao).all():
        raise ValueError("Categoria inexistente ou incoerente com tipo da transacao")
    for entity, column, methods in [("pagamentos", "metodo_pagamento", METHODS),
                                     ("recebimentos", "metodo_recebimento", ["PIX", "BOLETO", "TED", "TRANSFERENCIA", "DEPOSITO", "CHEQUE"])]:
        domain(normalized[entity], column, methods)
        validate_settlements(transactions, normalized[entity], entity)
    return normalized


def build_trusted(raw, previous=None, observed_on=None):
    previous = previous or {}
    observed_on = observed_on or date.today()
    raw = normalize_raw(raw)
    result = {}
    mappings = {
        "areas": ("id_area_natural", "area_sk", {"codigo_area": "id_area_natural"}),
        "categorias_contabeis": ("id_categoria_natural", "categoria_sk", {"id_categoria_raw": "id_categoria_natural"}),
        "fornecedores_clientes": ("id_parceiro_natural", "parceiro_sk", {
            "id_fornecedor_raw": "id_parceiro_natural", "cnpj_cpf": "documento", "contato": "contato_email", "telefone": "contato_telefone"}),
    }
    metadata = ["ingestion_id", "ingestion_ts", "source_entity", "row_seq", "raw_row_hash"]
    for entity, (natural, surrogate, rename) in mappings.items():
        frame = raw[entity].drop(columns=metadata, errors="ignore").rename(columns=rename)
        if entity == "areas":
            frame["codigo_area"] = frame.id_area_natural
        result[entity] = sync_dimension(frame, previous.get(entity), natural, surrogate, observed_on)
    currencies = pd.DataFrame([
        dict(codigo_iso="BRL", nome_moeda="Real Brasileiro", simbolo="R$", pais_referencia="Brasil"),
        dict(codigo_iso="USD", nome_moeda="Dolar Americano", simbolo="US$", pais_referencia="Estados Unidos"),
        dict(codigo_iso="EUR", nome_moeda="Euro", simbolo="€", pais_referencia="Zona do Euro"),
    ])
    result["moedas"] = sync_dimension(currencies, previous.get("moedas"), "codigo_iso", "moeda_sk", observed_on)
    employees = raw["funcionarios"].drop(columns=metadata, errors="ignore").rename(columns={"id_funcionario_raw": "id_funcionario_natural"})
    areas = result["areas"].query("is_current").set_index("id_area_natural").area_sk
    employees["area_sk"] = employees.departamento.map(areas)
    if employees.area_sk.isna().any():
        raise ValueError("Funcionario com area nao resolvida")
    employees["area_sk"] = employees.area_sk.astype(int)
    result["funcionarios"] = sync_dimension(employees, previous.get("funcionarios"), "id_funcionario_natural", "funcionario_sk", observed_on)
    transactions = raw["transacoes_financeiras"].drop(columns=metadata, errors="ignore").rename(columns={
        "id_transacao_raw": "id_transacao_natural", "codigo_area_raw": "id_area_natural",
        "id_fornecedor_raw": "id_parceiro_natural", "id_categoria_raw": "id_categoria_natural", "moeda": "codigo_iso", "descricao": "descricao_limpa"})
    transactions["descricao_limpa"] = transactions.descricao_limpa.str.replace(r"\s+", " ", regex=True).str.strip()
    prior = previous.get("transacoes_financeiras")
    transactions = stable_keys(transactions, prior, "id_transacao_natural", "transacao_sk")
    for entity, (natural, surrogate, _) in mappings.items():
        transactions = resolve_fk(transactions, result[entity], natural, surrogate, prior)
    transactions = resolve_fk(transactions, result["moedas"], "codigo_iso", "moeda_sk", prior)
    result["transacoes_financeiras"] = transactions
    for entity, natural, surrogate in [("pagamentos", "id_pagamento_natural", "pagamento_sk"),
                                       ("recebimentos", "id_recebimento_natural", "recebimento_sk")]:
        frame = raw[entity].drop(columns=metadata, errors="ignore").rename(columns={
            IDENTIFIERS[entity]: natural, "id_transacao_raw": "id_transacao_natural"})
        frame = stable_keys(frame, previous.get(entity), natural, surrogate)
        frame = frame.merge(transactions[["id_transacao_natural", "transacao_sk", "moeda_sk"]],
                            on="id_transacao_natural", how="left", validate="many_to_one")
        if frame.transacao_sk.isna().any():
            raise ValueError(f"{entity}: transacao nao resolvida")
        result[entity] = frame
    return result
