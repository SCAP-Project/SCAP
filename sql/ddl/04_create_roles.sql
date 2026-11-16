-- Configura grupos e permissões como administrador.
-- Substitua as senhas de exemplo apenas no ambiente local.
-- Os usuários nbeserra e acolumbari devem existir no cluster.

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'eng_dados')       THEN CREATE ROLE eng_dados       NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'cientista_dados') THEN CREATE ROLE cientista_dados NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_etl')         THEN CREATE ROLE app_etl         NOLOGIN; END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'leitura_bi')      THEN CREATE ROLE leitura_bi      NOLOGIN; END IF;
END
$$;

GRANT eng_dados, cientista_dados, app_etl TO CURRENT_USER;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'svc_etl') THEN
        CREATE ROLE svc_etl LOGIN PASSWORD 'TROQUE_SENHA_SVC_ETL' IN ROLE app_etl;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'svc_powerbi') THEN
        CREATE ROLE svc_powerbi LOGIN PASSWORD 'TROQUE_SENHA_SVC_POWERBI' IN ROLE leitura_bi;
    END IF;
END
$$;

GRANT eng_dados       TO nbeserra;
GRANT cientista_dados TO acolumbari;

CREATE SCHEMA IF NOT EXISTS ml AUTHORIZATION cientista_dados;

GRANT USAGE, CREATE ON SCHEMA raw, trusted, refined, ml TO eng_dados;
GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA raw, trusted, refined TO eng_dados;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO eng_dados;

GRANT USAGE ON SCHEMA raw, trusted, refined TO app_etl;
GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw, trusted, refined TO app_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO app_etl;

GRANT USAGE  ON SCHEMA raw, trusted, refined TO cientista_dados;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO cientista_dados;
GRANT USAGE  ON SCHEMA ml TO eng_dados;

GRANT USAGE  ON SCHEMA raw, trusted, refined TO leitura_bi;
GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO leitura_bi;

ALTER DEFAULT PRIVILEGES FOR ROLE eng_dados IN SCHEMA raw, trusted, refined
    GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON TABLES TO app_etl;
ALTER DEFAULT PRIVILEGES FOR ROLE eng_dados IN SCHEMA raw, trusted, refined
    GRANT USAGE, SELECT ON SEQUENCES TO app_etl;
ALTER DEFAULT PRIVILEGES FOR ROLE eng_dados IN SCHEMA raw, trusted, refined
    GRANT SELECT ON TABLES TO cientista_dados, leitura_bi;

ALTER DEFAULT PRIVILEGES FOR ROLE app_etl IN SCHEMA raw, trusted, refined
    GRANT ALL    ON TABLES TO eng_dados;
ALTER DEFAULT PRIVILEGES FOR ROLE app_etl IN SCHEMA raw, trusted, refined
    GRANT SELECT ON TABLES TO cientista_dados, leitura_bi;
