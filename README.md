# SCAP — Sistema de Crédito e Anomalias Preditivas

Projeto de TCC de Engenharia da Computação. Pipeline de dados financeiros
sintéticos para análise e detecção de anomalias de valor.

## Ambiente atual

O fluxo ativo usa CSVs locais. A conta AWS foi encerrada; RDS, EC2, túnel SSH
e `.env` não são necessários. Os scripts PostgreSQL ficam como histórico.

## Executar o ETL

Use Python 3.11 ou 3.12. Na raiz do repositório:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-csv.txt
python -m etl.csv_pipeline --generate
```

Para reprocessar os CSVs existentes, sem regenerar as fontes:

```powershell
python -m etl.csv_pipeline
python -m etl.csv_pipeline --validate-only
```

Mantenha os CSVs de trusted para preservar chaves e histórico. O manifesto
com contagens e hashes fica em `data/exports/etl_manifest.json`.

## Dados produzidos

| Fato em data/refined | Registros |
|---|---:|
| Transações financeiras | 39.792 |
| Pagamentos | 20.724 |
| Recebimentos | 18.681 |
| Saldos diários | 15.440 |

Também são produzidas seis dimensões: tempo, área, categoria contábil,
fornecedor/cliente, funcionário e moeda. Parcelas fecham em centavos e os
saldos incluem dias sem movimento, separados por área e moeda.

## Análise e modelos

O trabalho de ciência de dados está em [ml/README.md](ml/README.md): dez
notebooks de análise das tabelas, cinco notebooks de etapas e comparação
entre baseline histórico, Isolation Forest e autoencoder.

```powershell
python -m pip install -r ml/requirements.txt
python -m ml.run --stage all
```

Os notebooks são executáveis do início ao fim e têm visualizações azuis, sem
grade de fundo. [Resultados](ml/reports/RESULTADOS.md) registra as métricas,
a análise de erros e as limitações do experimento sintético.

## Testes

```powershell
python -m pip install pytest==7.4.3
python -m pytest -q
```

## Documentação e próximas entregas

- [ETL CSV](docs/development/ETL_CSV.md): comandos, tabelas e regras.
- [Ciência de dados](ml/README.md): notebooks, atributos e reprodução.
- [Roadmap](ROADMAP.md): entregas e pendências.
- [Contribuição](CONTRIBUTING.md): branches e revisão.

Próximas entregas: testar generalização em outro dataset reservado, dashboard
Power BI e redação do TCC. Os resultados atuais descrevem uma simulação;
não demonstram detecção de fraude ou risco real de inadimplência.
