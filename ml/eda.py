"""Exploracao especifica de cada uma das dez tabelas de refined."""

import numpy as np
import pandas as pd
from IPython.display import HTML, display

from .plotting import BLUE, LIGHT, NAVY, PALETTE, barh, canvas, compact, histogram, line, save_figure, style_table

TABLE_ORDER = ["dim_area", "dim_categoria_contabil", "dim_fornecedor_cliente", "dim_funcionario", "dim_moeda", "dim_tempo",
               "fact_transacoes_financeiras", "fact_pagamentos", "fact_recebimentos", "fact_saldos_diarios"]
TITLES = {"dim_area": "Áreas e concentração operacional", "dim_categoria_contabil": "Categorias contábeis",
          "dim_fornecedor_cliente": "Parceiros e cobertura de histórico", "dim_funcionario": "Quadro de funcionários",
          "dim_moeda": "Moedas e escopo financeiro", "dim_tempo": "Calendário e cobertura temporal",
          "fact_transacoes_financeiras": "Transações financeiras", "fact_pagamentos": "Pagamentos e prazos",
          "fact_recebimentos": "Recebimentos e parcelamento", "fact_saldos_diarios": "Fluxo de caixa e saldos"}
GRAINS = {"dim_area": "Versão diária de uma área", "dim_categoria_contabil": "Versão diária de uma categoria",
          "dim_fornecedor_cliente": "Versão diária de um parceiro", "dim_funcionario": "Versão diária de um funcionário",
          "dim_moeda": "Moeda de referência", "dim_tempo": "Dia do calendário", "fact_transacoes_financeiras": "Transação",
          "fact_pagamentos": "Evento de pagamento", "fact_recebimentos": "Evento de recebimento (parcela)",
          "fact_saldos_diarios": "Dia × versão de área × moeda"}


def overview(name, frame):
    coverage = "Cadastro" if "data" not in frame else f"{frame.data.min():%d/%m/%Y} — {frame.data.max():%d/%m/%Y}"
    cards = [("REGISTROS", f"{len(frame):,}".replace(",", ".")), ("COLUNAS", str(len(frame.columns))), ("COBERTURA", coverage)]
    html = '<div style="display:flex;gap:16px;margin:14px 0 22px;font-family:Arial">'
    for label, value in cards:
        html += f'<div style="flex:1;border-left:4px solid {BLUE};background:#F0F6FC;padding:14px 18px"><div style="font-size:10px;letter-spacing:1px;color:#60788E">{label}</div><div style="font-size:23px;font-weight:600;color:{NAVY};margin-top:7px">{value}</div></div>'
    display(HTML(html + "</div>"))


def profile(frame):
    return pd.DataFrame({"Coluna": frame.columns, "Tipo": frame.dtypes.astype(str).to_numpy(),
                         "Nulos": frame.isna().sum().to_numpy(), "Nulos (%)": (100 * frame.isna().mean()).round(2).to_numpy(),
                         "Distintos": frame.nunique().to_numpy()})


def current(frame):
    return frame[frame.is_current] if "is_current" in frame else frame


def analyze_table(name, tables):
    df = tables[name]
    fact = tables["fact_transacoes_financeiras"]
    figures, notes = [], []
    if name == "dim_area":
        activity = fact.groupby("area_sk").size().rename("Transações").to_frame().join(df.set_index("area_sk").nome_area)
        figures.append(barh(activity.set_index("nome_area").Transações, "Onde as transações se concentram", "As 12 áreas com mais lançamentos • sem duplicar versões de cadastro", "Transações"))
        figures.append(barh(fact.groupby("area_sk").valor_bruto.median().rename(index=df.set_index("area_sk").nome_area), "Tíquete mediano por área", "Mediana reduz a influência de valores extremos", "Valor bruto mediano (R$)"))
        share = activity.Transações.max() / len(fact)
        notes = [f"A área mais ativa reúne **{share:.1%}** das transações; o volume não se distribui igualmente entre áreas.",
                 "Área descreve a origem do lançamento; não identifica fraude. Use a chave da versão vinculada ao fato."]
    elif name == "dim_categoria_contabil":
        labels = df.set_index("categoria_sk").nome_categoria
        figures.append(barh(current(df).tipo_categoria.value_counts(), "Composição do cadastro contábil", "Quantidade de categorias por natureza", "Categorias", top=2))
        figures.append(barh(fact.groupby("categoria_sk").size().rename(index=labels), "Categorias mais utilizadas", "As 12 categorias com maior número de transações", "Transações"))
        joined = fact.merge(df[["categoria_sk", "tipo_categoria"]], on="categoria_sk", validate="many_to_one")
        mismatch = int(joined.tipo_transacao.ne(joined.tipo_categoria).sum())
        notes = [f"**{mismatch}** transações apresentam divergência entre tipo da transação e tipo da categoria.",
                 "Os nomes e as descrições são sintéticos; categorias descrevem contexto, não o rótulo de anomalia."]
    elif name == "dim_fornecedor_cliente":
        dim = current(df)
        used = set(fact.parceiro_sk)
        figures.append(barh(pd.Series({"Com transações": int(dim.parceiro_sk.isin(used).sum()), "Sem transações": int((~dim.parceiro_sk.isin(used)).sum())}), "Cobertura de histórico dos parceiros", "Cadastro atual versus presença no fato", "Parceiros", top=2))
        figures.append(barh(dim.tipo_parceiro.value_counts(), "Papéis comerciais do cadastro", "CLIENTE, FORNECEDOR ou AMBOS", "Parceiros", top=3))
        figures.append(barh(dim.rating_credito.value_counts(), "Distribuição do rating de cadastro", "Snapshot agregado com todo o histórico • excluído das features de treino", "Parceiros", top=8))
        notes = [f"**{fact.id_parceiro_natural.nunique()}** parceiros transacionam; os demais representam cadastros sem histórico.",
                 "Rating e prazo médio incorporam observações futuras em relação às transações antigas; não entram no modelo."]
    elif name == "dim_funcionario":
        employees = current(df)
        labels = tables["dim_area"].set_index("area_sk").nome_area
        figures.append(barh(employees.groupby("area_sk").size().rename(index=labels), "Distribuição do quadro por área", "Dimensão de RH: não há vínculo entre funcionário e transação", "Funcionários"))
        figures.append(histogram(employees.salario, "Distribuição dos salários", "Valores sintéticos • sem inferência sobre pessoas reais", "Salário (R$)"))
        figures.append(barh(employees.tipo_contrato.value_counts(), "Tipos de contrato", "Composição do quadro atual", "Funcionários", top=4))
        notes = [f"Salário mediano: **R$ {employees.salario.median():,.2f}**. Quadro atual: **{len(employees)} funcionários**.",
                 "Esta tabela é descritiva de RH e não será usada para prever anomalias de transação: o vínculo não existe na fonte."]
    elif name == "dim_moeda":
        counts = fact.groupby("moeda_sk").size().reindex(df.moeda_sk, fill_value=0)
        counts.index = df.codigo_iso
        figures.append(barh(counts, "Moedas usadas nas transações", "Ter uma moeda no cadastro não significa ter operações nessa moeda", "Transações", top=3))
        notes = [f"O cadastro contém **{len(df)} moedas**, mas há operações em **{fact.codigo_iso.nunique()}** moeda(s).",
                 "As análises financeiras deste snapshot estão em BRL. Não há taxa de câmbio para consolidar moedas diferentes."]
    elif name == "dim_tempo":
        figures.append(barh(df.groupby("ano").size().rename(index=lambda v: str(v)), "Cobertura do calendário", "Datas cadastradas por ano • calendário é mais amplo que a movimentação", "Dias", top=4))
        figures.append(line(fact.set_index("data").resample("MS").size().rename("Transações"), "Evolução mensal dos lançamentos", "Volume observado; a entrada e a saída de parceiros afetam a série", "Transações"))
        weekdays = fact.data.dt.dayofweek.value_counts().reindex(range(7), fill_value=0)
        weekdays.index = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
        figures.append(barh(weekdays, "Distribuição por dia da semana", "O gerador desloca lançamentos de fins de semana para dias úteis", "Transações", top=7))
        notes = [f"O calendário tem **{len(df)} dias**, de **{df.data.min():%d/%m/%Y}** a **{df.data.max():%d/%m/%Y}**.",
                 "`eh_feriado` é constante falso. Ausência de lançamentos no fim de semana é uma regra do gerador, não uma descoberta operacional."]
    elif name == "fact_transacoes_financeiras":
        figures.append(histogram(df.valor_bruto, "Distribuição dos valores brutos", "Eixo horizontal logarítmico • toda a distribuição, sem cortar extremos", "Valor bruto (R$, escala log)", log=True))
        monthly = df.groupby([pd.Grouper(key="data", freq="MS"), "tipo_transacao"]).valor_bruto.sum().unstack()
        figures.append(line(monthly, "Receitas e despesas por mês", "Valores de lançamento, não liquidações • séries separadas", "Valor bruto (R$)"))
        figures.append(barh(df.status_pagamento.value_counts(), "Situação dos lançamentos", "ATRASADO significa liquidado com atraso neste dataset", "Transações", top=3))
        notes = [f"Mediana: **R$ {df.valor_bruto.median():,.2f}**; percentil 99: **R$ {df.valor_bruto.quantile(.99):,.2f}**; máximo: **R$ {df.valor_bruto.max():,.2f}**.",
                 "Um valor alto pode ser habitual para certo parceiro. A detecção deve comparar o valor ao histórico disponível, e não apenas a um limite global."]
    elif name in ["fact_pagamentos", "fact_recebimentos"]:
        receipt = name == "fact_recebimentos"
        value = "valor_recebido" if receipt else "valor_pago"
        noun = "recebimentos" if receipt else "pagamentos"
        joined = df.merge(fact[["transacao_sk", "data", "valor_liquido", "status_pagamento"]], on="transacao_sk", suffixes=("", "_transacao"), validate="many_to_one")
        delay = (joined.data - joined.data_transacao).dt.days
        figures.append(line(df.set_index("data").resample("MS")[value].sum().rename(noun.capitalize()), f"Evolução mensal de {noun}", "Datas efetivas de liquidação • valores em BRL", "Valor liquidado (R$)"))
        figures.append(histogram(delay, "Prazo entre lançamento e liquidação", "Diferença em dias corridos • não há data de vencimento na origem", "Dias corridos"))
        counts = df.groupby("transacao_sk").size()
        figures.append(barh(counts.value_counts().rename(index=lambda n: f"{n} evento(s)"), "Eventos de liquidação por transação", "Duas linhas em recebimentos podem representar uma venda parcelada", "Transações", top=3))
        totals = joined.groupby("transacao_sk").agg(total=(value, "sum"), liquido=("valor_liquido", "first"), status=("status_pagamento", "first"))
        paid = totals[totals.status == "PAGO"]
        residual = (paid.total - paid.liquido).abs().max()
        notes = [f"**{len(df):,} eventos** para **{len(counts):,} transações**; prazo mediano de **{delay.median():.0f} dias**.",
                 f"Nas operações PAGO, diferença máxima entre a soma liquidada e o líquido: **R$ {residual:.2f}**."]
        if receipt:
            notes.append(f"**{int((counts == 2).sum()):,} transações** têm duas parcelas; sua soma foi conciliada pelo ETL. Pagamentos futuros não entram no modelo no instante da transação.")
        else:
            notes.append("Operações ATRASADO podem incluir acréscimos financeiros; a diferença para o líquido é prevista pelo gerador.")
    elif name == "fact_saldos_diarios":
        daily = df.groupby("data")[["saldo_final", "entradas", "saidas"]].sum()
        figures.append(line(daily.saldo_final.rename("Saldo acumulado"), "Trajetória do saldo consolidado", "Soma entre áreas em BRL • saldo inicial simulado igual a zero", "Saldo final (R$)", fill=True))
        figures.append(line(daily[["entradas", "saidas"]].resample("MS").sum().rename(columns={"entradas": "Entradas", "saidas": "Saídas"}), "Entradas e saídas mensais", "Medidas de fluxo podem ser somadas no tempo; saldo final não", "Valor (R$)"))
        last = df[df.data == df.data.max()].set_index("area_sk").saldo_final
        last.index = last.index.map(tables["dim_area"].set_index("area_sk").nome_area)
        fig, ax = canvas("Saldo por área no encerramento", f"Posição em {df.data.max():%d/%m/%Y} • valores podem ser negativos", size=(11, 6.5))
        ordered = last.sort_values()
        ax.barh(ordered.index, ordered.values, color=BLUE)
        ax.axvline(0, color=LIGHT, linewidth=1)
        ax.set_xlabel("Saldo final (R$)")
        from matplotlib.ticker import FuncFormatter
        ax.xaxis.set_major_formatter(FuncFormatter(compact))
        fig.subplots_adjust(left=0.28)
        figures.append(fig)
        residual = (df.saldo_final - df.saldo_inicial - df.entradas + df.saidas).abs().max()
        notes = [f"A série tem **{df.data.nunique()} dias**. Saldo consolidado no último dia: **R$ {daily.saldo_final.iloc[-1]:,.2f}**.",
                 f"Resíduo máximo da identidade contábil (antes de arredondar centavos): **{residual:.2e}**.",
                 "Saldo é uma posição: não some os saldos diários para obter movimentação. O saldo inicial zero é uma premissa da simulação."]
    for index, fig in enumerate(figures, 1):
        save_figure(fig, f"{name}_{index:02d}")
    return figures, notes
