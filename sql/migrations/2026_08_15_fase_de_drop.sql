-- Remove tabelas TRUSTED e REFINED somente se estiverem vazias.
-- Recrie as camadas com os DDLs 02 e 03 e reaplique 06_grants.sql.

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
