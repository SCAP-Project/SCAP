-- ===========================================================================
-- Migracao 2026-08-15 -- C3: chaves com tipo e nome honestos na camada raw
-- ===========================================================================
-- Alinha um banco JA EXISTENTE com a padronizacao das chaves feita nos
-- geradores. Banco NOVO nao precisa deste arquivo: 00 -> 06 em sql/ddl/ ja
-- criam tudo no formato certo.
--
-- COMO RODAR (como scap_admin, dono das tabelas). RODE ANTES da recarga:
--   python -m etl.utils.run_sql sql/migrations/2026_08_15_c3_chaves.sql --user scap_admin
--   python -m etl.load_raw.load_raw_csv_to_postgres
--
-- Idempotente: pode rodar mais de uma vez sem erro.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. id_transacao_raw: INT -> TEXT em pagamentos e recebimentos
-- ---------------------------------------------------------------------------
-- A fato guarda 'TR-00144'; estas duas guardavam 144. O ETL teria que
-- reconstruir a chave com "'TR-' || lpad(id::text, 5, '0')" toda vez que
-- precisasse juntar pagamento/recebimento com transacao -- regra fragil,
-- repetida em dois scripts, e com o tipo do DDL mentindo sobre o conteudo.
--
-- O USING converte o que ja esta la, entao a migracao funciona mesmo com dados
-- carregados. A recarga logo em seguida sobrescreve com o formato novo.
ALTER TABLE raw.pagamentos
    ALTER COLUMN id_transacao_raw TYPE TEXT
    USING CASE
        WHEN id_transacao_raw IS NULL THEN NULL
        ELSE 'TR-' || lpad(id_transacao_raw::text, 5, '0')
    END;

ALTER TABLE raw.recebimentos
    ALTER COLUMN id_transacao_raw TYPE TEXT
    USING CASE
        WHEN id_transacao_raw IS NULL THEN NULL
        ELSE 'TR-' || lpad(id_transacao_raw::text, 5, '0')
    END;

-- ---------------------------------------------------------------------------
-- 2. id_area_raw -> codigo_area_raw na fato
-- ---------------------------------------------------------------------------
-- A coluna sempre guardou o CODIGO da area ('FIN', 'TI'), nunca o id numerico
-- de raw.areas. Com o nome antigo, o join correto parecia um erro:
--     ON t.id_area_raw = a.codigo_area
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_schema = 'raw'
           AND table_name = 'transacoes_financeiras'
           AND column_name = 'id_area_raw'
    ) THEN
        ALTER TABLE raw.transacoes_financeiras RENAME COLUMN id_area_raw TO codigo_area_raw;
        RAISE NOTICE 'Coluna renomeada: id_area_raw -> codigo_area_raw';
    ELSE
        RAISE NOTICE 'Coluna codigo_area_raw ja existe -- nada a fazer';
    END IF;
END
$$;

COMMIT;

-- ---------------------------------------------------------------------------
-- 3. Conferencia
-- ---------------------------------------------------------------------------
-- Os dois devem retornar 'text':
--   SELECT data_type FROM information_schema.columns
--    WHERE table_schema='raw' AND table_name='pagamentos'
--      AND column_name='id_transacao_raw';
--
-- E este deve retornar 1 linha:
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema='raw' AND table_name='transacoes_financeiras'
--      AND column_name='codigo_area_raw';
