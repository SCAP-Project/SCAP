-- Migração histórica de chaves numéricas para o padrão textual.
-- Destinada ao esquema anterior à migração; não reaplique sobre chaves já prefixadas.
-- Execute antes de recarregar os CSVs. Bancos novos usam apenas sql/ddl.

BEGIN;

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
