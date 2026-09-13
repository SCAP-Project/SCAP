-- 05_create_ml_tables.sql
-- Schema ML: artefatos de experimento, nao fazem parte do Medallion.
-- O schema `ml` e criado em 04_create_roles.sql (owner: cientista_dados).

-- ============================================
-- GABARITO DE ANOMALIAS (ground truth)
-- ============================================
-- Rotulo do experimento controlado: quais transacoes tiveram o valor
-- deliberadamente distorcido pelo gerador de dados sinteticos.
--
-- POR QUE NAO FICA NO MEDALLION: um ERP real nao sabe dizer o que e anomalia.
-- Manter o rotulo fora de raw/trusted/refined preserva a simulacao fiel do
-- sistema-fonte e evita vazamento de rotulo (target leakage) no pipeline --
-- se `flag_anomalia` trafegasse junto com os dados, seria trivial construir
-- um modelo que "acerta" 100% simplesmente lendo a resposta.
--
-- USO: junta-se por id_transacao_raw APENAS na etapa de avaliacao, para
-- calcular precision / recall / F1 / AUC-ROC.
--
-- ORIGEM: data/ground_truth/transacoes_gabarito.csv, produzido por
-- etl/data_generation/generators/dados_transacoes_financeiras.ipynb

CREATE TABLE IF NOT EXISTS ml.transacoes_gabarito (
    id_transacao_raw TEXT PRIMARY KEY,
    data_transacao   DATE NOT NULL,

    -- Rotulo principal
    flag_anomalia    BOOLEAN NOT NULL,

    -- Mecanismo causal por tras de status_pagamento (documenta o processo
    -- gerador; util como feature de referencia e para analise de erro)
    perfil_risco     TEXT NOT NULL CHECK (perfil_risco IN (
        'normal', 'retencao', 'alto_valor', 'alto_valor_retencao'
    )),
    flag_ajuste      BOOLEAN NOT NULL,
    flag_alto_valor  BOOLEAN NOT NULL,

    -- Detalhe da injecao: NULL nas linhas normais.
    -- fator > 1 => valor inflado (70% dos casos); fator < 1 => reduzido (30%).
    fator_aplicado   NUMERIC(10,6),

    -- valor_original = antes da injecao; valor_bruto = o que foi para raw.
    -- Nas linhas normais os dois sao iguais.
    -- Precisao (18,6) preserva o valor como gerado; a camada trusted
    -- arredonda para DECIMAL(18,2).
    valor_original   NUMERIC(18,6) NOT NULL,
    valor_bruto      NUMERIC(18,6) NOT NULL,

    carregado_em     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Coerencia entre o rotulo e o detalhe da injecao
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

-- Leitura para engenharia de dados; escrita permanece com cientista_dados
-- (owner do schema ml). O app_etl precisa de escrita porque e ele quem carrega
-- o CSV do gabarito -- mesmo padrao das tabelas do Medallion.
GRANT USAGE ON SCHEMA ml TO app_etl;
GRANT SELECT ON ml.transacoes_gabarito TO eng_dados;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ml.transacoes_gabarito TO app_etl;
