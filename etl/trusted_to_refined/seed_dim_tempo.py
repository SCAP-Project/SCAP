"""Seed de dimensao: refined.dim_tempo (spine de datas 2023-01-01 a 2026-12-31).

Nao depende de trusted -- e uma dimensao gerada, nao extraida de origem. O
range cobre com folga o minimo exigido (2024-01-01 a 2026-02-10, onde
transacoes e recebimentos existem) e vai ate o fim de 2026 pra cobrir
qualquer analise/demo feita durante o TCC.

eh_feriado fica sempre FALSE: nao ha calendario de feriados moveis
(Carnaval, Pascoa, Corpus Christi) implementado neste escopo. eh_dia_util
considera so segunda-sexta.

Sem SCD Tipo 2 (a data de um dia nunca muda). Idempotente via
ON CONFLICT (data) DO NOTHING, inserido em lote com execute_values.

Uso:
    python -m etl.trusted_to_refined.seed_dim_tempo
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from psycopg2.extras import execute_values

from etl.config import get_engine, get_logger

log = get_logger(__name__)

DATA_INICIO = date(2023, 1, 1)
DATA_FIM = date(2026, 12, 31)

NOMES_MES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
NOMES_DIA_SEMANA = [
    "Segunda-feira", "Terça-feira", "Quarta-feira",
    "Quinta-feira", "Sexta-feira", "Sábado", "Domingo",
]

SQL_UPSERT = """
    INSERT INTO refined.dim_tempo
        (data, ano, semestre, trimestre, mes, nome_mes, dia, dia_semana,
         nome_dia_semana, semana_ano, eh_dia_util, eh_feriado,
         etl_batch_id, source_system)
    VALUES %s
    ON CONFLICT (data) DO NOTHING
"""


def _gerar_linhas(batch_id: str) -> list[tuple]:
    linhas = []
    dia_atual = DATA_INICIO
    while dia_atual <= DATA_FIM:
        weekday = dia_atual.weekday()  # 0=Segunda ... 6=Domingo
        linhas.append((
            dia_atual,
            dia_atual.year,
            1 if dia_atual.month <= 6 else 2,
            (dia_atual.month - 1) // 3 + 1,
            dia_atual.month,
            NOMES_MES[dia_atual.month - 1],
            dia_atual.day,
            weekday + 1,
            NOMES_DIA_SEMANA[weekday],
            dia_atual.isocalendar()[1],
            weekday < 5,
            False,
            batch_id,
            "SEED_GERADO",
        ))
        dia_atual += timedelta(days=1)
    return linhas


def main() -> None:
    batch_id = str(uuid.uuid4())
    linhas = _gerar_linhas(batch_id)

    raw_conn = get_engine().raw_connection()
    try:
        with raw_conn.cursor() as cur:
            execute_values(cur, SQL_UPSERT, linhas, page_size=1000)
        raw_conn.commit()
        log.info(
            "refined.dim_tempo: %d dia(s) gerado(s) (%s a %s), duplicatas ignoradas via ON CONFLICT",
            len(linhas), DATA_INICIO, DATA_FIM,
        )
    except Exception:
        raw_conn.rollback()
        log.exception("Falha no seed de dim_tempo -- rollback aplicado, nada foi persistido")
        raise
    finally:
        raw_conn.close()


if __name__ == "__main__":
    main()
