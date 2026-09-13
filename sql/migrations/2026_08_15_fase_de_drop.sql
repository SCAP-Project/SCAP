-- ===========================================================================
-- Migracao 2026-08-15 -- Fase D/E (DDL de trusted e refined)
-- ===========================================================================
-- Remove as tabelas de trusted e refined para que 02 e 03 possam recria-las
-- com a estrutura corrigida. As mudancas sao estruturais demais para ALTER:
-- colunas removidas (funcionario_sk, status_contabil, taxa_cambio,
-- numero_documento, data_demissao, status_funcionario), CHECKs trocados em
-- praticamente todas as tabelas, UNIQUEs de SCD2 adicionados e FKs que passam
-- a ser declaradas inline.
--
-- SEGURO: as duas camadas estao VAZIAS (0 linhas) e sao 100% reconstruiveis a
-- partir de raw pelo ETL. O bloco de verificacao abaixo aborta se houver
-- qualquer linha -- nao da para perder dado sem querer.
--
-- COMO RODAR (como scap_admin, dono das tabelas):
--   python -m etl.utils.run_sql \
--       sql/migrations/2026_08_15_fase_de_drop.sql \
--       sql/ddl/02_create_trusted_tables.sql \
--       sql/ddl/03_create_refined_tables.sql \
--       sql/ddl/06_grants.sql \
--       --user scap_admin
-- ===========================================================================

-- ---------------------------------------------------------------------------
-- 1. Trava de seguranca: aborta se houver dado em trusted/refined
-- ---------------------------------------------------------------------------
DO $$
DECLARE
    r      RECORD;
    n      BIGINT;
    total  BIGINT := 0;
BEGIN
    FOR r IN
        SELECT table_schema, table_name
          FROM information_schema.tables
         WHERE table_schema IN ('trusted', 'refined')
           AND table_type = 'BASE TABLE'
    LOOP
        EXECUTE format('SELECT count(*) FROM %I.%I', r.table_schema, r.table_name) INTO n;
        IF n > 0 THEN
            RAISE NOTICE '  % .% -> % linhas', r.table_schema, r.table_name, n;
        END IF;
        total := total + n;
    END LOOP;

    IF total > 0 THEN
        RAISE EXCEPTION
            'ABORTADO: existem % linhas em trusted/refined. Este script so roda com as camadas vazias.', total;
    END IF;

    RAISE NOTICE 'Verificacao OK: trusted e refined estao vazias, seguro recriar.';
END
$$;

-- ---------------------------------------------------------------------------
-- 2. Remocao (CASCADE resolve a ordem das FKs entre elas)
-- ---------------------------------------------------------------------------
DROP TABLE IF EXISTS refined.fact_saldos_diarios          CASCADE;
DROP TABLE IF EXISTS refined.fact_recebimentos            CASCADE;
DROP TABLE IF EXISTS refined.fact_pagamentos              CASCADE;
DROP TABLE IF EXISTS refined.fact_transacoes_financeiras  CASCADE;
DROP TABLE IF EXISTS refined.dim_funcionario              CASCADE;
DROP TABLE IF EXISTS refined.dim_fornecedor_cliente       CASCADE;
DROP TABLE IF EXISTS refined.dim_categoria_contabil       CASCADE;
DROP TABLE IF EXISTS refined.dim_area                     CASCADE;
DROP TABLE IF EXISTS refined.dim_moeda                    CASCADE;
DROP TABLE IF EXISTS refined.dim_tempo                    CASCADE;

DROP TABLE IF EXISTS trusted.recebimentos                 CASCADE;
DROP TABLE IF EXISTS trusted.pagamentos                   CASCADE;
DROP TABLE IF EXISTS trusted.transacoes_financeiras       CASCADE;
DROP TABLE IF EXISTS trusted.funcionarios                 CASCADE;
DROP TABLE IF EXISTS trusted.fornecedores_clientes        CASCADE;
DROP TABLE IF EXISTS trusted.categorias_contabeis         CASCADE;
DROP TABLE IF EXISTS trusted.areas                        CASCADE;
DROP TABLE IF EXISTS trusted.moedas                       CASCADE;
