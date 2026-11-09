# Auditoria e robustez

Esta etapa investiga por que os números originais são tão altos. Ela não
substitui os modelos, tabelas, escolhas ou métricas do primeiro experimento.

## Abrir os resultados

- [Relatório completo da rodada](reports/robustness/rodada_01/ROBUSTEZ.md).
- [Auditoria de vazamento](notebooks/robustness/01_auditoria_vazamento.ipynb).
- [Replicações e cenários difíceis](notebooks/robustness/02_cenarios_independentes.ipynb).
- [Ablação dos atributos](notebooks/robustness/03_ablacao_atributos.ipynb).
- [Conclusão](notebooks/robustness/04_conclusao_robustez.ipynb).

## O que foi avaliado

1. Recalcular históricos com filtros diretos e reproduzir scores/métricas.
2. Verificar whitelist, períodos, IDs, scaler e alterações de dados futuros.
3. Controle negativo com 100 permutações de rótulos.
4. Três novas seeds: 101, 202 e 303, com cinco cenários pareados por seed.
5. Retirada de grupos de atributos e referências de valor global/histórico.

Nos desafios, pesos, transformações e limiares permanecem congelados. O modelo
recebe apenas dados da nova fonte, usando o contexto de dias anteriores.
A avaliação adicional usa o segundo semestre de 2025. As ablações ajustam
variantes separadas apenas no treino e calibram na validação original; são
diagnósticos de um dataset que já foi inspecionado.

**Cenários:** original; anomalias sutis (10–30% de aumento ou redução);
extremos legítimos em cerca de 5% dos normais; mudança de regime para 30%
dos parceiros; combinação dessas condições com ruído normal extra.

A chave interna `so_historico` aparece como **Desvios atuais + histórico**:
inclui o valor atual relativo ao passado. O controle que efetivamente retira
o valor atual e seus derivados chama-se `sem_valor_atual`.

## Reproduzir

Com os artefatos do primeiro experimento já disponíveis:

```powershell
.\.venv\Scripts\python -m ml.robustness.run --stage all
```

As etapas também podem ser executadas separadamente:

```powershell
python -m ml.robustness.run --stage audit
python -m ml.robustness.run --stage challenges
python -m ml.robustness.run --stage ablations
python -m ml.robustness.run --stage report
python -m ml.robustness.run --stage notebooks
```

O padrão usa `rodada_01`. O registro local guarda configuração, métodos,
dependências, versões e hashes dos artefatos originais **antes** de gerar
as métricas. Se esses elementos mudarem, uma reexecução na mesma rodada
é rejeitada. Preserve-a e use outra pasta:

```powershell
python -m ml.robustness.run --run-id rodada_02 --stage all
```

Uma nova rodada não transforma datasets já inspecionados em teste inédito.
Para confirmar melhorias sugeridas pelos desafios atuais, reserve outra
fonte/seed/período antes de avaliar novamente.

## Saídas e limites

- `ml/reports/robustness/rodada_01/`: auditoria, protocolo, métricas,
  predições, ablações e relatório.
- `ml/artifacts/robustness/rodada_01/`: fontes sintéticas, gabaritos separados
  e modelos de ablação.
- `ml/reports/figures/robustness/rodada_01/`: PNG e SVG em azul, sem grade.
- Quatro novos notebooks executados e cópias HTML.

Cada seed é uma realização independente; seus cinco cenários são pareados.
As faixas entre três seeds não são intervalos de confiança. Outra seed do
mesmo gerador testa repetibilidade na simulação, não validação externa.
Picos legítimos e adulterações com as mesmas informações observáveis podem
ser indistinguíveis: isso exige discutir o alvo e o contexto disponível,
além do algoritmo. Os desafios atuais passam a ser dados de desenvolvimento
quando usados para sugerir melhorias.
