-- Migração histórica de atributos de parceiros.
-- Execute como proprietário das tabelas antes da recarga dos dados.

BEGIN;

ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS telefone       TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS cidade         TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS estado         TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS pais           TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS setor_atuacao  TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS rating_credito TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS prazo_medio    INT;

ALTER INDEX IF EXISTS raw.idx_transacao    RENAME TO idx_pag_transacao;
ALTER INDEX IF EXISTS raw.idx_ingestion_ts RENAME TO idx_trans_ingestion_ts;
ALTER INDEX IF EXISTS raw.idx_source       RENAME TO idx_trans_source;

CREATE INDEX IF NOT EXISTS idx_rec_transacao ON raw.recebimentos (id_transacao_raw);

COMMIT;
