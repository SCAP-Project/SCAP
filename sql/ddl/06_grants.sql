-- 06_grants.sql
-- Reaplica as permissoes sobre TODOS os objetos existentes do Medallion + ml.
--
-- POR QUE ISTO EXISTE SEPARADO: as permissoes do 04_create_roles.sql valem para
-- os objetos que existiam naquele momento, e os ALTER DEFAULT PRIVILEGES de la
-- foram definidos FOR ROLE eng_dados e FOR ROLE app_etl. Tabela criada pelo
-- MASTER (scap_admin) -- que e o caso quando se roda os DDLs como master --
-- nao cai em nenhuma dessas regras e nasce sem GRANT nenhum para o time.
--
-- Rode este arquivo sempre que recriar tabelas como scap_admin.
-- E idempotente: pode rodar quantas vezes quiser.
--
--   python -m etl.utils.run_sql sql/ddl/06_grants.sql --user scap_admin

-- ========== Uso dos schemas ==========
GRANT USAGE, CREATE ON SCHEMA raw, trusted, refined TO eng_dados;
GRANT USAGE ON SCHEMA raw, trusted, refined TO app_etl, cientista_dados, leitura_bi;
GRANT USAGE ON SCHEMA ml TO eng_dados, app_etl;

-- ========== Engenharia de dados: controle total no Medallion ==========
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA raw, trusted, refined TO eng_dados;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO eng_dados;
GRANT SELECT ON ALL TABLES IN SCHEMA ml TO eng_dados;

-- ========== Pipeline (svc_etl): read/write + TRUNCATE ==========
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw, trusted, refined TO app_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO app_etl;
-- O app_etl tambem carrega o gabarito em ml.transacoes_gabarito
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA ml TO app_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ml TO app_etl;

-- ========== Cientista de dados: leitura no Medallion, escrita no ml ==========
GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO cientista_dados;

-- ========== BI (svc_powerbi): somente leitura ==========
GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO leitura_bi;

-- ========== Objetos FUTUROS criados pelo MASTER ==========
-- Isto e o que faltava: sem estas linhas, toda tabela nova criada pelo
-- scap_admin nasce invisivel para o time ate alguem rodar um GRANT na mao.
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, trusted, refined
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, trusted, refined
    GRANT USAGE, SELECT ON SEQUENCES TO app_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, trusted, refined
    GRANT ALL ON TABLES TO eng_dados;
ALTER DEFAULT PRIVILEGES IN SCHEMA raw, trusted, refined
    GRANT SELECT ON TABLES TO cientista_dados, leitura_bi;
ALTER DEFAULT PRIVILEGES IN SCHEMA ml
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA ml
    GRANT SELECT ON TABLES TO eng_dados;
