-- ===========================================================================
-- Migracao 2026-08-15 -- Fase B (coerencia dos dados sinteticos)
-- ===========================================================================
-- Alinha um banco JA EXISTENTE com as mudancas de DDL da Fase B.
--
-- Banco NOVO nao precisa deste arquivo: basta rodar 00 -> 05 em sql/ddl/.
--
-- COMO RODAR: como usuario MASTER (scap_admin), conectado ao banco `scap`.
--   As tabelas pertencem a scap_admin, entao ALTER/CREATE exige esse usuario.
--   O svc_etl do .env so tem DML (grupo app_etl) e nao consegue aplicar isto.
--
--   psql -h localhost -p 5432 -U scap_admin -d scap -f sql/migrations/2026_08_15_fase_b.sql
--
-- Idempotente: pode rodar mais de uma vez sem erro.
-- ===========================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- 1. raw.fornecedores_clientes: colunas novas
-- ---------------------------------------------------------------------------
-- telefone, localizacao e setor passam a existir na origem (antes cidade/estado
-- so existiam embutidos na string de endereco). rating_credito e prazo_medio
-- sao derivados do comportamento observado do parceiro -- eram declarados em
-- trusted/refined sem nenhuma origem no raw.
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS telefone       TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS cidade         TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS estado         TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS pais           TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS setor_atuacao  TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS rating_credito TEXT;
ALTER TABLE raw.fornecedores_clientes ADD COLUMN IF NOT EXISTS prazo_medio    INT;

-- ---------------------------------------------------------------------------
-- 2. Indices do schema raw: nomes colidiam
-- ---------------------------------------------------------------------------
-- 'idx_transacao' era criado para raw.pagamentos E para raw.recebimentos. Nome
-- de indice e unico por schema, entao o segundo CREATE ... IF NOT EXISTS era
-- ignorado em silencio e raw.recebimentos ficava SEM indice.
ALTER INDEX IF EXISTS raw.idx_transacao    RENAME TO idx_pag_transacao;
ALTER INDEX IF EXISTS raw.idx_ingestion_ts RENAME TO idx_trans_ingestion_ts;
ALTER INDEX IF EXISTS raw.idx_source       RENAME TO idx_trans_source;

CREATE INDEX IF NOT EXISTS idx_rec_transacao ON raw.recebimentos (id_transacao_raw);

COMMIT;

-- ---------------------------------------------------------------------------
-- 3. Schema ml + tabela de gabarito
-- ---------------------------------------------------------------------------
-- Roda o arquivo de DDL do schema ml. Em psql:
--     \i sql/ddl/05_create_ml_tables.sql
--
-- (Nao da para dar \i dentro deste script de forma portavel; execute o comando
--  acima logo depois desta migracao.)

-- ---------------------------------------------------------------------------
-- 4. Conferencia
-- ---------------------------------------------------------------------------
-- Depois de aplicar, isto deve retornar 7 linhas:
--
--   SELECT column_name FROM information_schema.columns
--    WHERE table_schema='raw' AND table_name='fornecedores_clientes'
--      AND column_name IN ('telefone','cidade','estado','pais',
--                          'setor_atuacao','rating_credito','prazo_medio');
--
-- E isto deve mostrar idx_pag_transacao e idx_rec_transacao:
--
--   SELECT indexname FROM pg_indexes WHERE schemaname='raw' ORDER BY 1;
