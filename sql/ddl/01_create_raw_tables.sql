-- Criação das tabelas da camada RAW (Bronze)

-- Tabela: raw.transacoes_financeiras
CREATE TABLE IF NOT EXISTS raw.transacoes_financeiras (
    id_transacao_raw TEXT,      -- formato 'TR-00144'
    data_transacao TEXT,
    data_competencia TEXT,
    -- Guarda o CODIGO da area ('FIN', 'TI'), nao o id numerico de raw.areas.
    -- Antes se chamava id_area_raw, o que fazia o join parecer errado
    -- (t.id_area_raw = a.codigo_area). O nome agora diz o que a coluna e.
    codigo_area_raw TEXT,
    id_fornecedor_raw TEXT,
    tipo_transacao TEXT,
    valor_bruto TEXT, -- ok
    valor_liquido TEXT, -- ok
    moeda TEXT,
    descricao TEXT,
    id_categoria_raw TEXT,
    forma_pagamento TEXT,
    status_pagamento TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.transacoes_financeiras IS 'Transações financeiras brutas - Camada RAW';

-- Nomes de indice sao unicos POR SCHEMA: prefixar com a tabela evita colisao
-- silenciosa entre indices de tabelas diferentes do mesmo schema.
CREATE INDEX IF NOT EXISTS idx_trans_ingestion_ts ON raw.transacoes_financeiras (ingestion_ts);
CREATE INDEX IF NOT EXISTS idx_trans_source ON raw.transacoes_financeiras (source_system);

-- Tabela: raw.areas
CREATE TABLE IF NOT EXISTS raw.areas (
    id_area_raw INT,
    codigo_area TEXT,
    nome_area TEXT,
    gestor_responsavel TEXT,
    email_gestor TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.areas IS 'Áreas/departamentos brutos - Camada RAW';

-- Tabela: raw.fornecedores_clientes
CREATE TABLE IF NOT EXISTS raw.fornecedores_clientes (
    id_fornecedor_raw TEXT,
    nome_fornecedor TEXT,
    tipo_fornecedor TEXT,   -- CLIENTE | FORNECEDOR | AMBOS (derivado do fluxo real)
    cnpj_cpf TEXT,
    contato TEXT,           -- e-mail
    telefone TEXT,
    endereco TEXT,
    -- Localizacao em colunas proprias: antes so existia embutida na string de
    -- endereco, o que obrigaria o ETL a fazer parsing de texto.
    cidade TEXT,
    estado TEXT,
    pais TEXT,
    setor_atuacao TEXT,
    -- Atributos de credito derivados do comportamento observado do parceiro
    -- (inadimplencia e prazo medio de liquidacao). NULL/SEM_HISTORICO para os
    -- parceiros cadastrados que ainda nao transacionaram.
    rating_credito TEXT,
    prazo_medio INT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.fornecedores_clientes IS 'Fornecedores e clientes brutos - Camada RAW';

-- Tabela: raw.categorias_contabeis
CREATE TABLE IF NOT EXISTS raw.categorias_contabeis (
    id_categoria_raw INT,
    nome_categoria TEXT,
    tipo_categoria TEXT,
    codigo_contabil TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.categorias_contabeis IS 'Categorias contábeis brutas - Camada RAW';

-- Tabela: raw.pagamentos
CREATE TABLE IF NOT EXISTS raw.pagamentos (
    id_pagamento_raw INT,
    -- TEXT, no mesmo formato da fato ('TR-00144'). Era INT (144), o que
    -- obrigava o ETL a reconstruir a chave para conseguir juntar as tabelas.
    id_transacao_raw TEXT,
    data_pagamento TEXT,
    valor_pago TEXT,
    metodo_pagamento TEXT,
    comprovante TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.pagamentos IS 'Pagamentos brutos - Camada RAW';

CREATE INDEX IF NOT EXISTS idx_pag_transacao ON raw.pagamentos (id_transacao_raw);

-- Tabela: raw.recebimentos
CREATE TABLE IF NOT EXISTS raw.recebimentos (
    id_recebimento_raw INT,
    -- TEXT, no mesmo formato da fato ('TR-00144') -- ver raw.pagamentos.
    id_transacao_raw TEXT,
    data_recebimento TEXT,
    valor_recebido TEXT,
    metodo_recebimento TEXT,
    comprovante TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.recebimentos IS 'Recebimentos brutos - Camada RAW';

-- Antes este indice tambem se chamava 'idx_transacao', igual ao de raw.pagamentos.
-- Como o nome ja existia no schema, o CREATE INDEX IF NOT EXISTS era ignorado em
-- silencio e raw.recebimentos ficava SEM indice.
CREATE INDEX IF NOT EXISTS idx_rec_transacao ON raw.recebimentos (id_transacao_raw);

-- Tabela: raw.funcionarios
CREATE TABLE IF NOT EXISTS raw.funcionarios (
    id_funcionario_raw INT,
    nome TEXT,
    cpf TEXT,
    cargo TEXT,
    departamento TEXT,
    data_admissao TEXT,
    salario TEXT,
    tipo_contrato TEXT,
    ingestion_id CHAR(36) NOT NULL,
    ingestion_ts TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    source_entity TEXT NOT NULL,
    row_seq BIGINT,
    raw_row_hash TEXT
);

COMMENT ON TABLE raw.funcionarios IS 'Funcionários brutos - Camada RAW';