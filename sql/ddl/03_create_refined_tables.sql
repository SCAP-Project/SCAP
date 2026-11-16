-- Modelo dimensional REFINED; dimensões precedem os fatos.

CREATE TABLE IF NOT EXISTS refined.dim_tempo (
    tempo_sk BIGSERIAL PRIMARY KEY,
    data DATE NOT NULL UNIQUE,
    ano INT NOT NULL,
    semestre INT NOT NULL CHECK (semestre IN (1, 2)),
    trimestre INT NOT NULL CHECK (trimestre BETWEEN 1 AND 4),
    mes INT NOT NULL CHECK (mes BETWEEN 1 AND 12),
    nome_mes TEXT NOT NULL CHECK (nome_mes IN (
        'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
        'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
    )),
    dia INT NOT NULL CHECK (dia BETWEEN 1 AND 31),
    dia_semana INT NOT NULL CHECK (dia_semana BETWEEN 1 AND 7),
    nome_dia_semana TEXT NOT NULL CHECK (nome_dia_semana IN (
        'Segunda-feira', 'Terça-feira', 'Quarta-feira',
        'Quinta-feira', 'Sexta-feira', 'Sábado', 'Domingo'
    )),
    semana_ano INT NOT NULL CHECK (semana_ano BETWEEN 1 AND 53),
    eh_dia_util BOOLEAN NOT NULL DEFAULT TRUE,
    eh_feriado BOOLEAN NOT NULL DEFAULT FALSE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL DEFAULT 'SISTEMA'
);

COMMENT ON TABLE refined.dim_tempo IS 'Dimensão de tempo padronizada para todas as análises';
COMMENT ON COLUMN refined.dim_tempo.dia_semana IS '1=Segunda, 7=Domingo';

CREATE INDEX IF NOT EXISTS idx_dim_tempo_data ON refined.dim_tempo(data);
CREATE INDEX IF NOT EXISTS idx_dim_tempo_ano_mes ON refined.dim_tempo(ano, mes);

CREATE TABLE IF NOT EXISTS refined.dim_moeda (
    moeda_sk BIGSERIAL PRIMARY KEY,
    codigo_iso CHAR(3) NOT NULL UNIQUE,
    nome_moeda TEXT NOT NULL,
    simbolo TEXT,
    pais_referencia TEXT,

    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL
);

COMMENT ON TABLE refined.dim_moeda IS 'Reconstruída a partir de trusted.moedas; o de/para entre as duas camadas é feito por codigo_iso.';

CREATE TABLE IF NOT EXISTS refined.dim_area (
    area_sk BIGSERIAL PRIMARY KEY,
    id_area_natural TEXT NOT NULL,
    codigo_area TEXT NOT NULL,
    nome_area TEXT NOT NULL,
    gestor_responsavel TEXT,
    email_gestor TEXT,

    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_dim_area_natural_vigencia UNIQUE (id_area_natural, vigencia_inicio)
);

CREATE INDEX IF NOT EXISTS idx_dim_area_current ON refined.dim_area(is_current) WHERE is_current = TRUE;

CREATE TABLE IF NOT EXISTS refined.dim_categoria_contabil (
    categoria_sk BIGSERIAL PRIMARY KEY,
    id_categoria_natural TEXT NOT NULL,
    nome_categoria TEXT NOT NULL,
    tipo_categoria TEXT NOT NULL CHECK (tipo_categoria IN ('RECEITA', 'DESPESA')),
    codigo_contabil TEXT NOT NULL,

    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_dim_categoria_natural_vigencia UNIQUE (id_categoria_natural, vigencia_inicio)
);

CREATE INDEX IF NOT EXISTS idx_dim_categoria_current ON refined.dim_categoria_contabil(is_current) WHERE is_current = TRUE;

CREATE TABLE IF NOT EXISTS refined.dim_fornecedor_cliente (
    parceiro_sk BIGSERIAL PRIMARY KEY,
    id_parceiro_natural TEXT NOT NULL,
    nome_parceiro TEXT NOT NULL,
    tipo_parceiro TEXT NOT NULL CHECK (tipo_parceiro IN ('CLIENTE', 'FORNECEDOR', 'AMBOS')),
    documento TEXT,
    contato_email TEXT,
    contato_telefone TEXT,
    endereco TEXT,
    pais TEXT,
    estado TEXT,
    cidade TEXT,
    setor_atuacao TEXT,
    rating_credito TEXT CHECK (rating_credito IN (
        'AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'C', 'SEM_HISTORICO'
    )),
    prazo_medio INT CHECK (prazo_medio IS NULL OR prazo_medio >= 0),

    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_dim_parceiro_natural_vigencia UNIQUE (id_parceiro_natural, vigencia_inicio)
);

COMMENT ON COLUMN refined.dim_fornecedor_cliente.rating_credito IS 'Derivado da inadimplência observada - principal atributo de risco da dimensão';

CREATE INDEX IF NOT EXISTS idx_dim_fornecedor_current ON refined.dim_fornecedor_cliente(is_current) WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_dim_fornecedor_rating ON refined.dim_fornecedor_cliente(rating_credito);

CREATE TABLE IF NOT EXISTS refined.dim_funcionario (
    funcionario_sk BIGSERIAL PRIMARY KEY,
    id_funcionario_natural TEXT NOT NULL,
    nome TEXT NOT NULL,
    cpf TEXT NOT NULL,
    cargo TEXT NOT NULL,
    area_sk BIGINT NOT NULL REFERENCES refined.dim_area(area_sk),
    data_admissao DATE NOT NULL,
    tipo_contrato TEXT NOT NULL CHECK (tipo_contrato IN ('CLT', 'PJ', 'ESTAGIO', 'TEMPORARIO')),
    salario DECIMAL(18,2) CHECK (salario IS NULL OR salario > 0),

    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_dim_funcionario_natural_vigencia UNIQUE (id_funcionario_natural, vigencia_inicio)
);

COMMENT ON TABLE refined.dim_funcionario IS 'Dimensão de quadro de pessoal. Não se conecta aos fatos - a origem não vincula funcionário a transação.';

CREATE INDEX IF NOT EXISTS idx_dim_funcionario_current ON refined.dim_funcionario(is_current) WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_dim_funcionario_area ON refined.dim_funcionario(area_sk);

CREATE TABLE IF NOT EXISTS refined.fact_transacoes_financeiras (
    transacao_sk BIGSERIAL PRIMARY KEY,

    id_transacao_natural TEXT NOT NULL UNIQUE,

    tempo_sk BIGINT NOT NULL REFERENCES refined.dim_tempo(tempo_sk),
    area_sk BIGINT NOT NULL REFERENCES refined.dim_area(area_sk),
    parceiro_sk BIGINT NOT NULL REFERENCES refined.dim_fornecedor_cliente(parceiro_sk),
    categoria_sk BIGINT NOT NULL REFERENCES refined.dim_categoria_contabil(categoria_sk),
    moeda_sk BIGINT NOT NULL REFERENCES refined.dim_moeda(moeda_sk),

    valor_bruto DECIMAL(18,2) NOT NULL CHECK (valor_bruto > 0),
    valor_liquido DECIMAL(18,2) NOT NULL CHECK (valor_liquido > 0),

    tipo_transacao TEXT NOT NULL CHECK (tipo_transacao IN ('RECEITA', 'DESPESA')),
    forma_pagamento TEXT NOT NULL CHECK (forma_pagamento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO'
    )),
    status_pagamento TEXT NOT NULL CHECK (status_pagamento IN ('PAGO', 'ATRASADO', 'CANCELADO')),

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT ck_fact_transacoes_liquido_bruto CHECK (valor_liquido <= valor_bruto)
);

COMMENT ON TABLE refined.fact_transacoes_financeiras IS 'Fato principal: transações financeiras no nível de lançamento';

CREATE INDEX IF NOT EXISTS idx_fact_transacoes_tempo ON refined.fact_transacoes_financeiras(tempo_sk);
CREATE INDEX IF NOT EXISTS idx_fact_transacoes_area ON refined.fact_transacoes_financeiras(area_sk);
CREATE INDEX IF NOT EXISTS idx_fact_transacoes_parceiro ON refined.fact_transacoes_financeiras(parceiro_sk);
CREATE INDEX IF NOT EXISTS idx_fact_transacoes_categoria ON refined.fact_transacoes_financeiras(categoria_sk);
CREATE INDEX IF NOT EXISTS idx_fact_transacoes_status ON refined.fact_transacoes_financeiras(status_pagamento);

CREATE TABLE IF NOT EXISTS refined.fact_pagamentos (
    pagamento_sk BIGSERIAL PRIMARY KEY,
    id_pagamento_natural TEXT NOT NULL UNIQUE,

    tempo_sk BIGINT NOT NULL REFERENCES refined.dim_tempo(tempo_sk),
    transacao_sk BIGINT NOT NULL REFERENCES refined.fact_transacoes_financeiras(transacao_sk),

    parceiro_sk BIGINT NOT NULL REFERENCES refined.dim_fornecedor_cliente(parceiro_sk),
    moeda_sk BIGINT NOT NULL REFERENCES refined.dim_moeda(moeda_sk),

    valor_pago DECIMAL(18,2) NOT NULL CHECK (valor_pago > 0),

    metodo_pagamento TEXT NOT NULL CHECK (metodo_pagamento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO'
    )),
    comprovante TEXT,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_pagamentos_tempo ON refined.fact_pagamentos(tempo_sk);
CREATE INDEX IF NOT EXISTS idx_fact_pagamentos_transacao ON refined.fact_pagamentos(transacao_sk);

CREATE TABLE IF NOT EXISTS refined.fact_recebimentos (
    recebimento_sk BIGSERIAL PRIMARY KEY,
    id_recebimento_natural TEXT NOT NULL UNIQUE,

    tempo_sk BIGINT NOT NULL REFERENCES refined.dim_tempo(tempo_sk),
    transacao_sk BIGINT NOT NULL REFERENCES refined.fact_transacoes_financeiras(transacao_sk),
    parceiro_sk BIGINT NOT NULL REFERENCES refined.dim_fornecedor_cliente(parceiro_sk),
    moeda_sk BIGINT NOT NULL REFERENCES refined.dim_moeda(moeda_sk),

    valor_recebido DECIMAL(18,2) NOT NULL CHECK (valor_recebido > 0),

    metodo_recebimento TEXT NOT NULL CHECK (metodo_recebimento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'DEPOSITO', 'CHEQUE'
    )),
    comprovante TEXT,

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_fact_recebimentos_tempo ON refined.fact_recebimentos(tempo_sk);
CREATE INDEX IF NOT EXISTS idx_fact_recebimentos_transacao ON refined.fact_recebimentos(transacao_sk);

CREATE TABLE IF NOT EXISTS refined.fact_saldos_diarios (
    saldo_sk BIGSERIAL PRIMARY KEY,

    tempo_sk BIGINT NOT NULL REFERENCES refined.dim_tempo(tempo_sk),
    area_sk BIGINT NOT NULL REFERENCES refined.dim_area(area_sk),
    moeda_sk BIGINT NOT NULL REFERENCES refined.dim_moeda(moeda_sk),

    saldo_inicial DECIMAL(18,2) NOT NULL,
    saldo_final DECIMAL(18,2) NOT NULL,
    entradas DECIMAL(18,2) NOT NULL CHECK (entradas >= 0),
    saidas DECIMAL(18,2) NOT NULL CHECK (saidas >= 0),

    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,

    CONSTRAINT uq_saldos_dia_area_moeda UNIQUE (tempo_sk, area_sk, moeda_sk),

    CONSTRAINT ck_saldos_identidade CHECK (saldo_final = saldo_inicial + entradas - saidas)
);

COMMENT ON TABLE refined.fact_saldos_diarios IS 'Snapshot de saldos consolidados por dia, área e moeda - derivado de fact_pagamentos e fact_recebimentos';

CREATE INDEX IF NOT EXISTS idx_fact_saldos_tempo ON refined.fact_saldos_diarios(tempo_sk);
CREATE INDEX IF NOT EXISTS idx_fact_saldos_area ON refined.fact_saldos_diarios(area_sk);

COMMENT ON SCHEMA refined IS 'Camada REFINED (Gold): Modelo dimensional otimizado para análises, BI e machine learning';
