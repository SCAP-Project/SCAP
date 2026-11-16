-- Estruturas de avaliação de ML; gabarito separado das camadas de dados.

CREATE TABLE IF NOT EXISTS ml.transacoes_gabarito (
    id_transacao_raw TEXT PRIMARY KEY,
    data_transacao   DATE NOT NULL,

    flag_anomalia    BOOLEAN NOT NULL,

    perfil_risco     TEXT NOT NULL CHECK (perfil_risco IN (
        'normal', 'retencao', 'alto_valor', 'alto_valor_retencao'
    )),
    flag_ajuste      BOOLEAN NOT NULL,
    flag_alto_valor  BOOLEAN NOT NULL,

    fator_aplicado   NUMERIC(10,6),

    valor_original   NUMERIC(18,6) NOT NULL,
    valor_bruto      NUMERIC(18,6) NOT NULL,

    carregado_em     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_gabarito_fator_coerente CHECK (
        (flag_anomalia AND fator_aplicado IS NOT NULL)
        OR (NOT flag_anomalia AND fator_aplicado IS NULL)
    )
);

COMMENT ON TABLE  ml.transacoes_gabarito IS 'Ground truth de anomalias do dataset sintetico - uso restrito a avaliacao de modelo';
COMMENT ON COLUMN ml.transacoes_gabarito.flag_anomalia IS 'TRUE se a transacao teve o valor distorcido na geracao';
COMMENT ON COLUMN ml.transacoes_gabarito.perfil_risco IS 'Perfil que determinou as probabilidades de status_pagamento';
COMMENT ON COLUMN ml.transacoes_gabarito.fator_aplicado IS 'Multiplicador da injecao; NULL nas transacoes normais';
COMMENT ON COLUMN ml.transacoes_gabarito.valor_original IS 'valor_bruto antes da injecao de anomalia';

CREATE INDEX IF NOT EXISTS idx_gabarito_flag  ON ml.transacoes_gabarito (flag_anomalia);
CREATE INDEX IF NOT EXISTS idx_gabarito_data  ON ml.transacoes_gabarito (data_transacao);

GRANT USAGE ON SCHEMA ml TO app_etl;
GRANT SELECT ON ml.transacoes_gabarito TO eng_dados;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ml.transacoes_gabarito TO app_etl;
