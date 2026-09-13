-- 02_create_trusted_tables.sql
-- Criação das tabelas da camada TRUSTED (Silver)
--
-- ORDEM DE CRIAÇÃO: as tabelas referenciadas vêm antes das que referenciam, e
-- todas as FKs são declaradas INLINE. A versão anterior criava as tabelas e
-- depois adicionava as FKs de moeda com ALTER TABLE ... ADD CONSTRAINT (sem
-- IF NOT EXISTS), o que fazia o script quebrar na segunda execução. Junto com
-- os CREATE INDEX IF NOT EXISTS, o arquivo agora é reexecutável.
--
-- DOMÍNIOS: todos os CHECK foram conferidos contra os valores reais em raw.*
-- (SELECT DISTINCT). A versão anterior declarava, por exemplo,
-- status_pagamento IN ('Pago','Pendente','Cancelado') enquanto os dados traziam
-- 'PAGO'/'ATRASADO'/'CANCELADO' -- rejeitava as 39.792 transações.

-- ============================================
-- 1. trusted.moedas (referência, sem dependências)
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.moedas (
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

COMMENT ON TABLE trusted.moedas IS 'Moedas de referência. O escopo atual é operação nacional (todas as transações em BRL); a tabela existe para extensibilidade.';

-- ============================================
-- 2. trusted.areas (SCD Tipo 2)
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.areas (
    area_sk BIGSERIAL PRIMARY KEY,
    id_area_natural TEXT NOT NULL,
    codigo_area TEXT NOT NULL,
    nome_area TEXT NOT NULL,
    gestor_responsavel TEXT,
    email_gestor TEXT,
    -- SCD Tipo 2: Controle de histórico
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    -- Metadados de auditoria
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    -- Impede duas versões da mesma área com a mesma vigência
    CONSTRAINT uq_areas_natural_vigencia UNIQUE (id_area_natural, vigencia_inicio)
);

COMMENT ON TABLE trusted.areas IS 'Áreas/departamentos com histórico (SCD Tipo 2)';
COMMENT ON COLUMN trusted.areas.area_sk IS 'Surrogate Key (PK)';
COMMENT ON COLUMN trusted.areas.id_area_natural IS 'Código da área no ERP (chave natural). A fato referencia a área pelo CÓDIGO (ex.: FIN), não por id numérico.';
COMMENT ON COLUMN trusted.areas.is_current IS 'Flag indicando se é a versão atual (SCD2)';

CREATE INDEX IF NOT EXISTS idx_areas_natural ON trusted.areas(id_area_natural);
CREATE INDEX IF NOT EXISTS idx_areas_current ON trusted.areas(is_current) WHERE is_current = TRUE;

-- ============================================
-- 3. trusted.categorias_contabeis (SCD Tipo 2)
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.categorias_contabeis (
    categoria_sk BIGSERIAL PRIMARY KEY,
    id_categoria_natural TEXT NOT NULL,
    nome_categoria TEXT NOT NULL,
    tipo_categoria TEXT NOT NULL CHECK (tipo_categoria IN ('RECEITA', 'DESPESA')),
    codigo_contabil TEXT NOT NULL,
    -- SCD Tipo 2
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_categorias_natural_vigencia UNIQUE (id_categoria_natural, vigencia_inicio)
);

CREATE INDEX IF NOT EXISTS idx_categorias_natural ON trusted.categorias_contabeis(id_categoria_natural);
CREATE INDEX IF NOT EXISTS idx_categorias_current ON trusted.categorias_contabeis(is_current) WHERE is_current = TRUE;

-- ============================================
-- 4. trusted.fornecedores_clientes (SCD Tipo 2)
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.fornecedores_clientes (
    parceiro_sk BIGSERIAL PRIMARY KEY,
    id_parceiro_natural TEXT NOT NULL,
    nome_fornecedor TEXT NOT NULL,
    -- AMBOS é valor legítimo: o parceiro que aparece nos dois fluxos (compra e
    -- venda). O tipo é derivado do comportamento observado, não do prefixo do id.
    tipo_fornecedor TEXT NOT NULL CHECK (tipo_fornecedor IN ('CLIENTE', 'FORNECEDOR', 'AMBOS')),
    documento TEXT,
    contato_email TEXT,
    contato_telefone TEXT,
    endereco TEXT,
    pais TEXT,
    estado TEXT,
    cidade TEXT,
    setor_atuacao TEXT,
    -- Atributos de crédito derivados do histórico do parceiro:
    -- rating a partir da taxa de inadimplência (ATRASADO + CANCELADO) e
    -- prazo_medio a partir dos dias entre transação e liquidação.
    -- SEM_HISTORICO = parceiro cadastrado que ainda não transacionou.
    rating_credito TEXT CHECK (rating_credito IN (
        'AAA', 'AA', 'A', 'BBB', 'BB', 'B', 'C', 'SEM_HISTORICO'
    )),
    prazo_medio INTEGER CHECK (prazo_medio IS NULL OR prazo_medio >= 0),
    -- SCD Tipo 2
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_parceiros_natural_vigencia UNIQUE (id_parceiro_natural, vigencia_inicio)
);

COMMENT ON TABLE trusted.fornecedores_clientes IS 'Cadastro de fornecedores/clientes com histórico';
COMMENT ON COLUMN trusted.fornecedores_clientes.tipo_fornecedor IS 'CLIENTE, FORNECEDOR ou AMBOS - derivado do fluxo real das transações';
COMMENT ON COLUMN trusted.fornecedores_clientes.rating_credito IS 'Derivado da taxa de inadimplência observada; SEM_HISTORICO quando não há transações';
COMMENT ON COLUMN trusted.fornecedores_clientes.prazo_medio IS 'Média de dias entre a transação e sua liquidação; NULL sem histórico';

CREATE INDEX IF NOT EXISTS idx_parceiros_natural ON trusted.fornecedores_clientes(id_parceiro_natural);
CREATE INDEX IF NOT EXISTS idx_parceiros_current ON trusted.fornecedores_clientes(is_current) WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_parceiros_rating ON trusted.fornecedores_clientes(rating_credito);

-- ============================================
-- 5. trusted.funcionarios (SCD Tipo 2)
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.funcionarios (
    funcionario_sk BIGSERIAL PRIMARY KEY,
    id_funcionario_natural TEXT NOT NULL,
    nome TEXT NOT NULL,
    cpf TEXT NOT NULL,
    cargo TEXT NOT NULL,
    area_sk BIGINT NOT NULL REFERENCES trusted.areas(area_sk),
    data_admissao DATE NOT NULL,
    -- ESTAGIO sem acento, igual à origem: valor de domínio acentuado é fonte
    -- recorrente de bug de encoding entre CSV, Python e Postgres. O rótulo
    -- bonito é responsabilidade da camada de apresentação.
    tipo_contrato TEXT NOT NULL CHECK (tipo_contrato IN ('CLT', 'PJ', 'ESTAGIO', 'TEMPORARIO')),
    -- Recuperado da origem: existe em raw.funcionarios e havia sido descartado.
    salario DECIMAL(18,2) CHECK (salario IS NULL OR salario > 0),
    -- SCD Tipo 2
    vigencia_inicio DATE NOT NULL DEFAULT CURRENT_DATE,
    vigencia_fim DATE,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    CONSTRAINT uq_funcionarios_natural_vigencia UNIQUE (id_funcionario_natural, vigencia_inicio)
);

-- REMOVIDOS: data_demissao e status_funcionario. Não existem na origem e, sem
-- ela, status_funcionario seria constante 'ATIVO' em 150 de 150 linhas --
-- coluna que não discrimina nada.
COMMENT ON TABLE trusted.funcionarios IS 'Quadro de funcionários com histórico (SCD Tipo 2)';
COMMENT ON COLUMN trusted.funcionarios.area_sk IS 'Área do funcionário, resolvida pelo código do departamento na origem';

CREATE INDEX IF NOT EXISTS idx_funcionarios_natural ON trusted.funcionarios(id_funcionario_natural);
CREATE INDEX IF NOT EXISTS idx_funcionarios_current ON trusted.funcionarios(is_current) WHERE is_current = TRUE;
CREATE INDEX IF NOT EXISTS idx_funcionarios_area ON trusted.funcionarios(area_sk);

-- ============================================
-- 6. trusted.transacoes_financeiras
-- ============================================
CREATE TABLE IF NOT EXISTS trusted.transacoes_financeiras (
    transacao_sk BIGSERIAL PRIMARY KEY,
    id_transacao_natural TEXT NOT NULL UNIQUE,
    -- Foreign Keys
    area_sk BIGINT NOT NULL REFERENCES trusted.areas(area_sk),
    parceiro_sk BIGINT NOT NULL REFERENCES trusted.fornecedores_clientes(parceiro_sk),
    categoria_sk BIGINT NOT NULL REFERENCES trusted.categorias_contabeis(categoria_sk),
    moeda_sk BIGINT NOT NULL REFERENCES trusted.moedas(moeda_sk),
    -- REMOVIDO: funcionario_sk. A origem não associa funcionário a transação, e
    -- metade das áreas não tem quadro de funcionários -- o vínculo seria
    -- inventado. Análises de RH seguem por trusted.funcionarios x trusted.areas.
    -- Datas padronizadas
    data_transacao DATE NOT NULL,
    data_competencia DATE NOT NULL,
    -- Valores financeiros (a origem já grava com 2 casas)
    valor_bruto DECIMAL(18,2) NOT NULL CHECK (valor_bruto > 0),
    valor_liquido DECIMAL(18,2) NOT NULL CHECK (valor_liquido > 0),
    -- REMOVIDOS: taxa_cambio (sem origem e sem sentido com base 100% BRL),
    -- numero_documento (sem origem) e status_contabil (sem origem; derivá-lo da
    -- competência daria valor único para quase toda a base).
    -- Atributos padronizados
    tipo_transacao TEXT NOT NULL CHECK (tipo_transacao IN ('RECEITA', 'DESPESA')),
    forma_pagamento TEXT NOT NULL CHECK (forma_pagamento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO'
    )),
    status_pagamento TEXT NOT NULL CHECK (status_pagamento IN ('PAGO', 'ATRASADO', 'CANCELADO')),
    descricao_limpa TEXT NOT NULL,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL,
    -- O líquido é o bruto menos desconto: nunca pode superá-lo
    CONSTRAINT ck_transacoes_liquido_bruto CHECK (valor_liquido <= valor_bruto)
);

COMMENT ON COLUMN trusted.transacoes_financeiras.descricao_limpa IS 'Descrição da transação após limpeza de texto';
COMMENT ON COLUMN trusted.transacoes_financeiras.status_pagamento IS 'PAGO, ATRASADO ou CANCELADO. ATRASADO é o sinal mais relevante para risco de crédito.';

CREATE INDEX IF NOT EXISTS idx_transacoes_data ON trusted.transacoes_financeiras(data_transacao);
CREATE INDEX IF NOT EXISTS idx_transacoes_competencia ON trusted.transacoes_financeiras(data_competencia);
CREATE INDEX IF NOT EXISTS idx_transacoes_tipo ON trusted.transacoes_financeiras(tipo_transacao);
CREATE INDEX IF NOT EXISTS idx_transacoes_status ON trusted.transacoes_financeiras(status_pagamento);
CREATE INDEX IF NOT EXISTS idx_transacoes_parceiro ON trusted.transacoes_financeiras(parceiro_sk);
CREATE INDEX IF NOT EXISTS idx_transacoes_area ON trusted.transacoes_financeiras(area_sk);

-- ============================================
-- 7. trusted.pagamentos
-- ============================================
-- Existe pagamento se, e somente se, a DESPESA foi liquidada (PAGO ou ATRASADO).
CREATE TABLE IF NOT EXISTS trusted.pagamentos (
    pagamento_sk BIGSERIAL PRIMARY KEY,
    id_pagamento_natural TEXT NOT NULL UNIQUE,
    transacao_sk BIGINT NOT NULL REFERENCES trusted.transacoes_financeiras(transacao_sk),
    moeda_sk BIGINT NOT NULL REFERENCES trusted.moedas(moeda_sk),
    data_pagamento DATE NOT NULL,
    valor_pago DECIMAL(18,2) NOT NULL CHECK (valor_pago > 0),
    metodo_pagamento TEXT NOT NULL CHECK (metodo_pagamento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'CARTAO'
    )),
    comprovante TEXT,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pagamentos_data ON trusted.pagamentos(data_pagamento);
CREATE INDEX IF NOT EXISTS idx_pagamentos_transacao ON trusted.pagamentos(transacao_sk);

-- ============================================
-- 8. trusted.recebimentos
-- ============================================
-- Existe recebimento se, e somente se, a RECEITA foi liquidada (PAGO ou
-- ATRASADO). Uma transação pode ter 2 parcelas, então a relação é 1:N.
CREATE TABLE IF NOT EXISTS trusted.recebimentos (
    recebimento_sk BIGSERIAL PRIMARY KEY,
    id_recebimento_natural TEXT NOT NULL UNIQUE,
    transacao_sk BIGINT NOT NULL REFERENCES trusted.transacoes_financeiras(transacao_sk),
    moeda_sk BIGINT NOT NULL REFERENCES trusted.moedas(moeda_sk),
    data_recebimento DATE NOT NULL,
    valor_recebido DECIMAL(18,2) NOT NULL CHECK (valor_recebido > 0),
    metodo_recebimento TEXT NOT NULL CHECK (metodo_recebimento IN (
        'PIX', 'BOLETO', 'TED', 'TRANSFERENCIA', 'DEPOSITO', 'CHEQUE'
    )),
    comprovante TEXT,
    -- Metadados
    etl_batch_id UUID,
    criado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_recebimentos_data ON trusted.recebimentos(data_recebimento);
CREATE INDEX IF NOT EXISTS idx_recebimentos_transacao ON trusted.recebimentos(transacao_sk);

COMMENT ON SCHEMA trusted IS 'Camada TRUSTED (Silver): Dados limpos e integrados - Single Source of Truth';
