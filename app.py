"""Raio-X Bovinu'S | página inicial.

Rodar:  streamlit run app.py
"""
import streamlit as st

from core.seed import garantir_banco

st.set_page_config(page_title="Raio-X Bovinu'S", page_icon="🍖", layout="wide")
garantir_banco()

st.title("Raio-X Bovinu'S")
st.subheader("Dados do salão para decisões melhores")

st.markdown(
    "A Bovinu'S sabe o peso de cada prato e o total do caixa, mas não sabe **o que foi servido**, "
    "**quanto tempo as mesas ficam sujas** nem **o que o cliente achou**. "
    "Este sistema coleta esses dados sem dar trabalho para a equipe."
)

c1, c2 = st.columns(2)
with c1:
    st.markdown("#### 1. Raio-X do Prato")
    st.write("Foto do prato na balança + IA → composição, custo e margem de cada prato.")
    st.page_link("pages/1_Raio-X_do_Prato.py", label="Abrir a balança")

    st.markdown("#### 3. Controle das mesas")
    st.write("O garçom marca 'cliente saiu' e 'limpa' → tempo de mesa suja.")
    st.page_link("pages/3_Mesas.py", label="Abrir o mapa de mesas")
with c2:
    st.markdown("#### 2. Avaliação do cliente")
    st.write("QR Code na mesa: nota da comida, do tempo de espera e dos itens do buffet.")
    st.page_link("pages/2_Avaliacao.py", label="Abrir a avaliação")

    st.markdown("#### 4. Painel do gerente")
    st.write("Tudo reunido em indicadores e gráficos.")
    st.page_link("pages/4_Painel_do_Gerente.py", label="Abrir o painel")

st.caption("Dados anteriores marcados como 'simulado' são fictícios e servem apenas para demonstração.")
