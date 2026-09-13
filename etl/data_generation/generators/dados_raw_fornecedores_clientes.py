#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np
import hashlib
import uuid
import os
import glob
import random
from datetime import datetime

SEED = 42
random.seed(SEED)
np.random.seed(SEED)

QTD_TOTAL     = 250
SOURCE_SYSTEM = 'ERP_CORPORATIVO'
SOURCE_ENTITY = 'parceiros'
INGESTION_TS  = datetime(2026, 1, 10, 9, 0, 0).strftime('%Y-%m-%dT%H:%M:%S.000Z')

# A7: ingestion_id deterministico (era uuid.uuid4(), que mudava a cada execucao)
NAMESPACE_SCAP = uuid.uuid5(uuid.NAMESPACE_DNS, 'scap-project.tcc')
INGESTION_ID   = str(uuid.uuid5(NAMESPACE_SCAP, f'{SOURCE_ENTITY}|2026-01-10'))

print(f'ingestion_id : {INGESTION_ID}')
print(f'ingestion_ts : {INGESTION_TS}')


# In[2]:


# A raiz do projeto e localizada subindo ate achar a pasta 'sql' (marcador do
# repo). Antes era os.path.join(os.getcwd(), '..', '..'), que so acertava
# quando o script rodava a partir de etl/data_generation/ -- rodando de
# generators/ (onde o arquivo mora) os CSVs iam parar em etl/data/.
def achar_raiz(marcador='sql'):
    caminho = os.path.abspath(os.getcwd())
    while True:
        if os.path.isdir(os.path.join(caminho, marcador)):
            return caminho
        pai = os.path.dirname(caminho)
        if pai == caminho:
            raise RuntimeError(
                f"raiz do projeto nao encontrada (marcador '{marcador}') "
                f"a partir de {os.getcwd()}"
            )
        caminho = pai

workspace = achar_raiz()

# ORDEM DE GERACAO: este script agora roda DEPOIS de pagamentos e recebimentos.
# Antes ele so lia as transacoes e sorteava tipo_fornecedor pelo prefixo do id.
# Agora tipo_fornecedor, rating_credito e prazo_medio sao DERIVADOS do
# comportamento observado do parceiro (decisao D2), o que exige as datas de
# liquidacao -- que so existem em pagamentos/recebimentos.
fato_dir  = os.path.join(workspace, 'data', 'raw', 'transacoes_financeiras')
fato_csvs = sorted(glob.glob(os.path.join(fato_dir, '*.csv')))

df_fato = pd.concat(
    [pd.read_csv(f, usecols=['id_transacao_raw', 'id_fornecedor_raw',
                             'tipo_transacao', 'status_pagamento',
                             'data_transacao']) for f in fato_csvs],
    ignore_index=True,
)
df_fato['data_transacao']   = pd.to_datetime(df_fato['data_transacao'])

df_pag = pd.read_csv(os.path.join(workspace, 'data', 'raw', 'pagamentos', 'pagamentos.csv'),
                     usecols=['id_transacao_raw', 'data_pagamento'])
df_rec = pd.read_csv(os.path.join(workspace, 'data', 'raw', 'recebimentos', 'recebimentos.csv'),
                     usecols=['id_transacao_raw', 'data_recebimento'])

df_liquidacao = pd.concat([
    df_pag.rename(columns={'data_pagamento': 'data_liquidacao'}),
    df_rec.rename(columns={'data_recebimento': 'data_liquidacao'}),
], ignore_index=True)
df_liquidacao['data_liquidacao'] = pd.to_datetime(df_liquidacao['data_liquidacao'])

# Uma transacao pode ter 2 parcelas: a primeira liquidacao define o prazo.
df_liquidacao = (df_liquidacao
                 .sort_values('data_liquidacao')
                 .drop_duplicates('id_transacao_raw', keep='first'))

ids_existentes = sorted(df_fato['id_fornecedor_raw'].astype(str).unique())

print(f'Transacoes: {len(df_fato):,} | Liquidacoes: {len(df_liquidacao):,}')
print(f'Parceiros com historico: {len(ids_existentes)}')


# In[3]:


# ---- Perfil comportamental por parceiro ----------------------------------
df_perfil = df_fato.merge(
    df_liquidacao, on='id_transacao_raw', how='left',
)
df_perfil['dias_liquidacao'] = (
    df_perfil['data_liquidacao'] - df_perfil['data_transacao']
).dt.days

agg = df_perfil.groupby('id_fornecedor_raw').agg(
    qtd_transacoes=('id_transacao_raw', 'size'),
    qtd_despesa=('tipo_transacao', lambda s: (s == 'DESPESA').sum()),
    qtd_receita=('tipo_transacao', lambda s: (s == 'RECEITA').sum()),
    qtd_atrasado=('status_pagamento', lambda s: (s == 'ATRASADO').sum()),
    qtd_cancelado=('status_pagamento', lambda s: (s == 'CANCELADO').sum()),
    prazo_medio=('dias_liquidacao', 'mean'),
)

# B2: tipo derivado do fluxo real. DESPESA = a empresa paga -> o parceiro e
# FORNECEDOR. RECEITA = a empresa recebe -> o parceiro e CLIENTE. Os dois
# fluxos -> AMBOS. Antes o tipo saia do prefixo do id (FORN-/ACC-/numerico),
# sem relacao com as transacoes: dava 8.029 RECEITAs de FORNECEDOR.
def classificar_tipo(linha):
    if linha['qtd_despesa'] > 0 and linha['qtd_receita'] > 0:
        return 'AMBOS'
    return 'FORNECEDOR' if linha['qtd_despesa'] > 0 else 'CLIENTE'

agg['tipo_fornecedor'] = agg.apply(classificar_tipo, axis=1)

# D2: rating de credito derivado da inadimplencia observada.
agg['taxa_inadimplencia'] = (agg['qtd_atrasado'] + agg['qtd_cancelado']) / agg['qtd_transacoes']

# Faixas calibradas sobre a distribuicao REAL de inadimplencia deste dataset
# (min 0,04 | p25 0,17 | mediana 0,20 | p75 0,23 | max 0,33). Uma escala
# generica (AAA<=0,05 ... B<=0,40) jogava 83% dos parceiros em BBB/BB e deixava
# 1 unico AAA -- rating quase constante nao discrimina risco e seria inutil
# como feature. Estas faixas distribuem os 200 parceiros pelos 7 graus.
FAIXAS_RATING = [
    (0.12, 'AAA'), (0.15, 'AA'), (0.18, 'A'),
    (0.21, 'BBB'), (0.24, 'BB'), (0.28, 'B'),
]

def classificar_rating(taxa):
    for limite, rotulo in FAIXAS_RATING:
        if taxa <= limite:
            return rotulo
    return 'C'

agg['rating_credito'] = agg['taxa_inadimplencia'].apply(classificar_rating)
agg['prazo_medio'] = agg['prazo_medio'].round().astype('Int64')

print('Parceiros por tipo (derivado do fluxo real):')
print(agg['tipo_fornecedor'].value_counts().to_string())
print()
print('Parceiros por rating (derivado da inadimplencia):')
print(agg['rating_credito'].value_counts().sort_index().to_string())
print()
print('Prazo medio de liquidacao (dias):')
print(agg['prazo_medio'].describe().round(2).to_string())


# In[4]:


PREFIXOS_EMPRESAS = [
    'Tech', 'Data', 'Global', 'Prime', 'Alpha', 'Beta', 'Nexo', 'Vox',
    'Sigma', 'Apex', 'Nova', 'Flex', 'Core', 'Link', 'Smart', 'Pro',
    'Mega', 'Ultra', 'Max', 'Top', 'Net', 'Info', 'Soft', 'Cloud',
    'Digital', 'Connect', 'Power', 'Fast', 'Sure', 'Safe',
]
SUFIXOS_EMPRESAS = [
    'Solutions', 'Systems', 'Consulting', 'Services', 'Technologies',
    'Brasil', 'Group', 'Partners', 'Logística', 'Comercial',
    'Assessoria', 'Ltda', 'S.A.', 'Indústria', 'Distribuidora',
    'Engenharia', 'Contábil', 'Financeira', 'Holding', 'Gestão',
]
CIDADES_ESTADOS = [
    ('São Paulo', 'SP'), ('Rio de Janeiro', 'RJ'), ('Belo Horizonte', 'MG'),
    ('Curitiba', 'PR'), ('Porto Alegre', 'RS'), ('Salvador', 'BA'),
    ('Fortaleza', 'CE'), ('Recife', 'PE'), ('Manaus', 'AM'), ('Goiânia', 'GO'),
    ('Brasília', 'DF'), ('Campinas', 'SP'), ('Santos', 'SP'), ('Florianópolis', 'SC'),
]
TIPOS_LOGRADOURO = ['Rua', 'Av.', 'Alameda', 'Travessa', 'Rodovia']

# B7: setor de atuacao passa a existir na origem. cidade/estado/pais tambem
# viram colunas proprias -- antes so existiam embutidos na string de endereco
# ("Rua Corporativa 3245, Florianópolis - SC"), o que obrigaria o ETL a fazer
# parsing de texto para popular trusted.fornecedores_clientes.
SETORES = [
    'Tecnologia', 'Indústria', 'Comércio', 'Serviços', 'Logística',
    'Construção', 'Saúde', 'Educação', 'Agronegócio', 'Financeiro',
]

def gerar_nome_empresa(rng_seed):
    r = random.Random(rng_seed)
    return f"{r.choice(PREFIXOS_EMPRESAS)} {r.choice(SUFIXOS_EMPRESAS)}"

def gerar_cnpj(n):
    """Gera CNPJ fictício no formato 14 dígitos (sem validação)."""
    return str(n).zfill(14)

def gerar_email(nome, idx):
    slug = nome.lower().replace(' ', '.').replace('/', '').replace('á','a') \
                .replace('ã','a').replace('ç','c').replace('é','e') \
                .replace('ê','e').replace('ó','o').replace('ô','o') \
                .replace('ú','u').replace('í','i')[:30]
    return f'contato{idx}@{slug}.com.br'

def gerar_telefone(idx):
    r = random.Random(idx + 7000)
    return f'({r.randint(11, 99)}) 9{r.randint(1000, 9999)}-{r.randint(1000, 9999)}'

def gerar_localizacao(idx):
    r = random.Random(idx + 1000)
    tipo = r.choice(TIPOS_LOGRADOURO)
    num  = r.randint(1, 9999)
    cidade, estado = r.choice(CIDADES_ESTADOS)
    endereco = f'{tipo} Corporativa {num}, {cidade} - {estado}'
    return endereco, cidade, estado

def gerar_setor(idx):
    return random.Random(idx + 3000).choice(SETORES)

def gerar_hash(row_dict):
    campos = ['id_fornecedor_raw', 'nome_fornecedor', 'tipo_fornecedor', 'cnpj_cpf']
    conteudo = '|'.join(str(row_dict.get(c, '')) for c in campos)
    return hashlib.sha256(conteudo.encode('utf-8')).hexdigest()

print('Funções auxiliares definidas.')


# In[5]:


def montar_registro(id_forn, idx, seed_nome, tipo, rating, prazo, cnpj_base):
    nome = gerar_nome_empresa(seed_nome)
    endereco, cidade, estado = gerar_localizacao(idx)
    row = {
        'id_fornecedor_raw': id_forn,
        'nome_fornecedor':   nome,
        'tipo_fornecedor':   tipo,
        'cnpj_cpf':          gerar_cnpj(cnpj_base),
        'contato':           gerar_email(nome, idx),
        'telefone':          gerar_telefone(idx),
        'endereco':          endereco,
        'cidade':            cidade,
        'estado':            estado,
        'pais':              'Brasil',
        'setor_atuacao':     gerar_setor(idx),
        'rating_credito':    rating,
        'prazo_medio':       prazo,
    }
    row['raw_row_hash'] = gerar_hash(row)
    return row

registros_existentes = []
for idx, id_forn in enumerate(ids_existentes, start=1):
    perfil = agg.loc[id_forn]
    registros_existentes.append(montar_registro(
        id_forn, idx, seed_nome=idx,
        tipo=perfil['tipo_fornecedor'],
        rating=perfil['rating_credito'],
        prazo=perfil['prazo_medio'],
        cnpj_base=idx * 100 + 1000,
    ))

print(f'Registros com histórico: {len(registros_existentes)}')


# In[6]:


# Parceiros recem-cadastrados: existem no cadastro mas ainda nao transacionaram.
# Sem historico nao ha rating nem prazo -- e isso e informacao, nao lacuna.
novos_forn = [f'FORN-{i:05d}' for i in range(201, 218)]
novos_acc  = [f'ACC-{i:05d}'  for i in range(201, 217)]
novos_num  = [str(1000200 + i) for i in range(1, 18)]

novos_ids = novos_forn + novos_acc + novos_num
assert len(novos_ids) == 50, f'Esperado 50 novos, gerado {len(novos_ids)}'

def tipo_por_prefixo(id_str):
    if id_str.startswith('ACC'):
        return 'CLIENTE'
    return 'FORNECEDOR'

registros_novos = []
for offset, id_forn in enumerate(novos_ids, start=len(ids_existentes) + 1):
    registros_novos.append(montar_registro(
        id_forn, offset, seed_nome=offset + 9999,
        tipo=tipo_por_prefixo(id_forn),
        rating='SEM_HISTORICO',
        prazo=pd.NA,
        cnpj_base=offset * 100 + 5000,
    ))

print(f'Registros sem histórico: {len(registros_novos)}')


# In[7]:


todos_registros = registros_existentes + registros_novos

for seq, row in enumerate(todos_registros, start=1):
    row['ingestion_id']  = INGESTION_ID
    row['ingestion_ts']  = INGESTION_TS
    row['source_system'] = SOURCE_SYSTEM
    row['source_entity'] = SOURCE_ENTITY
    row['row_seq']       = seq

COLUNAS = [
    'id_fornecedor_raw', 'nome_fornecedor', 'tipo_fornecedor', 'cnpj_cpf',
    'contato', 'telefone', 'endereco', 'cidade', 'estado', 'pais',
    'setor_atuacao', 'rating_credito', 'prazo_medio',
    'ingestion_id', 'ingestion_ts', 'source_system', 'source_entity',
    'row_seq', 'raw_row_hash',
]
df_forn = pd.DataFrame(todos_registros, columns=COLUNAS)

print(f'Shape final: {df_forn.shape}')
df_forn.head()


# In[8]:


assert len(df_forn) == QTD_TOTAL, f'Esperado {QTD_TOTAL}, gerado {len(df_forn)}'

ids_gerados = set(df_forn['id_fornecedor_raw'].astype(str))
ausentes    = [i for i in ids_existentes if i not in ids_gerados]
assert len(ausentes) == 0, f'IDs ausentes: {ausentes[:5]}'

assert df_forn['id_fornecedor_raw'].nunique() == QTD_TOTAL, 'IDs duplicados!'
assert df_forn['cnpj_cpf'].nunique() == QTD_TOTAL, 'CNPJs duplicados!'
assert df_forn['tipo_fornecedor'].isin(['CLIENTE', 'FORNECEDOR', 'AMBOS']).all()
assert df_forn.loc[df_forn['rating_credito'] == 'SEM_HISTORICO', 'prazo_medio'].isna().all()

print('Todos os IDs da tabela fato estão presentes.')
print('Sem IDs duplicados.')
print()
print('Distribuição por tipo_fornecedor:')
print(df_forn['tipo_fornecedor'].value_counts().to_string())
print()
print('Distribuição por rating_credito:')
print(df_forn['rating_credito'].value_counts().sort_index().to_string())
print()
print('Distribuição por setor_atuacao:')
print(df_forn['setor_atuacao'].value_counts().to_string())


# In[9]:


output_dir  = os.path.join(workspace, 'data', 'raw', 'fornecedores_clientes')
os.makedirs(output_dir, exist_ok=True)

output_path = os.path.join(output_dir, 'fornecedores_clientes.csv')
df_forn.to_csv(output_path, index=False, encoding='utf-8')

print(f'Arquivo exportado: {output_path}')
print(f'Total de registros: {len(df_forn)}')
