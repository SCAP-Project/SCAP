-- Permissões do pipeline e da análise; requer as roles de 04_create_roles.sql.

GRANT USAGE, CREATE ON SCHEMA raw, trusted, refined TO eng_dados;
GRANT USAGE ON SCHEMA raw, trusted, refined TO app_etl, cientista_dados, leitura_bi;
GRANT USAGE ON SCHEMA ml TO eng_dados, app_etl;

GRANT ALL PRIVILEGES ON ALL TABLES    IN SCHEMA raw, trusted, refined TO eng_dados;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO eng_dados;
GRANT SELECT ON ALL TABLES IN SCHEMA ml TO eng_dados;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA raw, trusted, refined TO app_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA raw, trusted, refined TO app_etl;

GRANT SELECT, INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA ml TO app_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ml TO app_etl;

GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO cientista_dados;

GRANT SELECT ON ALL TABLES IN SCHEMA raw, trusted, refined TO leitura_bi;

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
