"""Historico diario de cadastro e chaves estaveis para arquivos CSV."""

from datetime import date

import pandas as pd


def stable_keys(frame, previous, natural, surrogate):
    result = frame.copy()
    if previous is not None and not previous.empty:
        removed = set(previous[natural]) - set(result[natural])
        if removed:
            raise ValueError(f"Remocao de fatos nao suportada ({natural}); use outra pasta data para outro dataset")
    old = {} if previous is None or previous.empty else dict(zip(previous[natural], previous[surrogate].astype(int)))
    next_key = max(old.values(), default=0) + 1
    keys = []
    for value in result[natural]:
        if value not in old:
            old[value] = next_key
            next_key += 1
        keys.append(old[value])
    result[surrogate] = keys
    return result


def sync_dimension(incoming, previous, natural, surrogate, observed_on: date):
    """SCD2 por dia de observacao; correcoes no mesmo dia mantem a chave.

    Intervalos [inicio, fim). Nao se infere o cadastro de uma data anterior
    a primeira carga. Versoes antigas continuam disponiveis para os fatos.
    """
    today = observed_on.isoformat()
    incoming = incoming.sort_values(natural).reset_index(drop=True)
    if incoming[natural].duplicated().any():
        raise ValueError(f"Chave de dimensao duplicada: {natural}")
    records = [] if previous is None else previous.to_dict("records")
    for row in records:
        row[surrogate] = int(row[surrogate])
        row["is_current"] = str(row["is_current"]).lower() == "true"
        row["vigencia_fim"] = "" if pd.isna(row["vigencia_fim"]) else row["vigencia_fim"]
    if any(str(row["vigencia_inicio"]) > today or str(row["vigencia_fim"]) > today for row in records):
        raise ValueError("Data de observacao anterior ao historico existente")
    current = {}
    for row in records:
        if row["is_current"]:
            if row[natural] in current:
                raise ValueError(f"Mais de uma versao atual: {row[natural]}")
            current[row[natural]] = row
    next_key = max((row[surrogate] for row in records), default=0) + 1
    business = [column for column in incoming if column != "source_system"]
    for row in incoming.to_dict("records"):
        existing = current.get(row[natural])
        if existing and all(str(existing.get(c, "")) == str(row[c]) for c in business):
            continue
        if existing and str(existing["vigencia_inicio"]) == today:
            existing.update(row)
            continue
        if existing:
            existing.update(is_current=False, vigencia_fim=today)
        new = dict(row, **{surrogate: next_key, "vigencia_inicio": today,
                          "vigencia_fim": "", "is_current": True})
        next_key += 1
        records.append(new)
    present = set(incoming[natural])
    for row in records:
        if row["is_current"] and row[natural] not in present:
            row.update(is_current=False, vigencia_fim=today)
    return pd.DataFrame(records).sort_values(surrogate).reset_index(drop=True)


def resolve_fk(frame, dimension, natural, surrogate, previous=None):
    """Preserva a versao vinculada se a chave natural da transacao nao mudou."""
    result = frame.copy()
    current = dimension[dimension.is_current]
    mapping = dict(zip(current[natural], current[surrogate]))
    result[surrogate] = result[natural].map(mapping)
    if previous is not None and not previous.empty:
        prior = previous.set_index("id_transacao_natural")
        old_natural = result.id_transacao_natural.map(prior[natural])
        old_key = result.id_transacao_natural.map(prior[surrogate].astype(int))
        keep = old_natural.eq(result[natural]) & old_key.notna()
        result.loc[keep, surrogate] = old_key[keep]
    if result[surrogate].isna().any() or not result[surrogate].isin(dimension[surrogate]).all():
        raise ValueError(f"Dimensao nao resolvida: {natural}")
    result[surrogate] = result[surrogate].astype(int)
    return result
