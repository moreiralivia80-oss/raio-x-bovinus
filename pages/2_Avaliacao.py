"""Módulo 2: Avaliação do cliente (aberta pelo QR Code da mesa).

O QR de cada mesa aponta para:  <url-do-app>/Avaliacao?mesa=12
"""
import streamlit as st

from core import db
from core.ia import classificar_comentario
from core.seed import garantir_banco

st.set_page_config(page_title="Avalie sua experiência", page_icon="🍖", initial_sidebar_state="collapsed")
garantir_banco()

mesa_param = st.query_params.get("mesa")
mesa = int(mesa_param) if mesa_param and str(mesa_param).isdigit() else None

st.title("Como foi sua refeição?")
st.write("Ao final da refeição, se puder, avalie sua experiência. **A Bovinu'S agradece!**")

if st.session_state.get("avaliacao_enviada"):
    st.success("Obrigado pela sua avaliação! Volte sempre.")
    if st.button("Enviar outra avaliação"):
        st.session_state["avaliacao_enviada"] = False
        st.rerun()
    st.stop()

nomes_itens = db.itens()["nome"].tolist()

with st.form("avaliacao"):
    if mesa is None:
        mesa = st.number_input("Número da mesa", min_value=1, max_value=90, step=1)
    else:
        st.caption(f"Mesa {mesa}")

    st.markdown("**O que achou da comida?**")
    nota_comida = st.feedback("stars", key="nota_comida")
    st.markdown("**O que achou do tempo de espera?**")
    nota_espera = st.feedback("stars", key="nota_espera")

    gostou = st.pills("Qual item você mais gostou?", nomes_itens, selection_mode="multi")
    nao_gostou = st.pills("Algum item não estava bom?", nomes_itens, selection_mode="multi")
    comentario = st.text_area("Comentário (opcional)", max_chars=300)

    enviar = st.form_submit_button("Enviar avaliação", type="primary", width="stretch")

if enviar:
    if nota_comida is None or nota_espera is None:
        st.warning("Por favor, dê uma nota para a comida e para o tempo de espera.")
    else:
        assunto = classificar_comentario(comentario)
        # st.feedback("stars") devolve de 0 a 4; somamos 1 para ficar de 1 a 5
        db.salvar_avaliacao(int(mesa), nota_comida + 1, nota_espera + 1,
                            gostou or [], nao_gostou or [], comentario.strip(), assunto)
        st.session_state["avaliacao_enviada"] = True
        st.rerun()
