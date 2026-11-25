"""Módulo 4: Painel do gerente."""
import pandas as pd
import streamlit as st

from core import calculos
from core.seed import garantir_banco

st.set_page_config(page_title="Painel do gerente", page_icon="🍖", layout="wide")
garantir_banco()

st.title("Painel do gerente")

dias = calculos.dias_com_dados()
opcoes = ["Todo o período"] + dias
escolha = st.selectbox("Período", opcoes,
                       format_func=lambda d: d if d == "Todo o período" else pd.to_datetime(d).strftime("%d/%m/%Y"))
dia = None if escolha == "Todo o período" else escolha

pratos = calculos.pratos_periodo(dia)
servidos = calculos.itens_periodo(dia)
avaliacoes = calculos.avaliacoes_periodo(dia)
limpeza = calculos.tempos_limpeza(dia)

# ---------- indicadores ----------
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Pratos analisados", f"{len(pratos):,}".replace(",", "."))
k2.metric("Custo médio por prato", f"R$ {pratos['custo_estimado'].mean():.2f}" if len(pratos) else "–")
k3.metric("Margem média estimada", f"{pratos['margem'].mean() * 100:.1f}%" if len(pratos) else "–")
k4.metric("Tempo médio de mesa suja", f"{limpeza['minutos'].mean():.1f} min" if len(limpeza) else "–")
k5.metric("Nota média da comida", f"{avaliacoes['nota_comida'].mean():.1f} / 5" if len(avaliacoes) else "–")

aba_prato, aba_aval, aba_mesas = st.tabs(["Raio-X do Prato", "Avaliações", "Mesas"])

# ---------- Raio-X do Prato ----------
with aba_prato:
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**Mix do prato: % do peso servido x % do custo**")
        st.bar_chart(calculos.mix_por_categoria(servidos), stack=False)
        st.caption("Quando uma categoria tem % do custo bem maior que % do peso, ela pesa no lucro.")
    with c2:
        st.markdown("**Itens que mais pesam no custo**")
        st.dataframe(calculos.itens_que_mais_custam(servidos), hide_index=True, width="stretch",
                     column_config={"item": "Item", "categoria": "Categoria",
                                    "peso_kg": st.column_config.NumberColumn("Peso servido (kg)", format="%.1f"),
                                    "custo": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f")})
    if len(pratos):
        por_hora = (pratos.assign(hora=pd.to_datetime(pratos["momento"], format="ISO8601").dt.hour)
                    .groupby("hora").agg(pratos=("id", "count"), margem=("margem", "mean")))
        st.markdown("**Pratos por horário**")
        st.bar_chart(por_hora["pratos"])

# ---------- Avaliações ----------
with aba_aval:
    if avaliacoes.empty:
        st.info("Ainda não há avaliações neste período.")
    else:
        c1, c2, c3 = st.columns(3)
        c1.metric("Avaliações", len(avaliacoes))
        c2.metric("Nota da comida", f"{avaliacoes['nota_comida'].mean():.1f} / 5")
        c3.metric("Nota do tempo de espera", f"{avaliacoes['nota_espera'].mean():.1f} / 5")

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Itens mais criticados e mais elogiados**")
            st.dataframe(calculos.ranking_itens_avaliados(dia), hide_index=True, width="stretch",
                         column_config={"item": "Item", "elogios": "Elogios", "criticas": "Críticas"})
        with c2:
            st.markdown("**Assunto dos comentários (classificado pela IA)**")
            st.bar_chart(avaliacoes["assunto"].dropna().value_counts())

        st.markdown("**Nota do tempo de espera por horário**")
        notas_hora = (avaliacoes.assign(hora=pd.to_datetime(avaliacoes["momento"], format="ISO8601").dt.hour)
                      .groupby("hora")[["nota_comida", "nota_espera"]].mean().round(2))
        st.line_chart(notas_hora)

        st.markdown("**Últimos comentários**")
        ultimos = (avaliacoes[avaliacoes["comentario"].fillna("") != ""]
                   .sort_values("momento", ascending=False)
                   [["momento", "mesa", "nota_comida", "nota_espera", "assunto", "comentario"]].head(10))
        st.dataframe(ultimos, hide_index=True, width="stretch")

# ---------- Mesas ----------
with aba_mesas:
    if limpeza.empty:
        st.info("Ainda não há registros de limpeza neste período.")
    else:
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Tempo médio de mesa suja por salão (min)**")
            st.bar_chart(limpeza.groupby("salao")["minutos"].mean().round(1))
        with c2:
            st.markdown("**Tempo médio de mesa suja por horário (min)**")
            st.bar_chart(limpeza.groupby("hora")["minutos"].mean().round(1))

st.caption("Registros com origem 'simulado' são fictícios e servem apenas para demonstração.")
