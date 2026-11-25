"""Módulo 1: Raio-X do Prato (tela da balança)."""
import streamlit as st

from core import calculos, db
from core.ia import analisar_prato
from core.seed import garantir_banco

st.set_page_config(page_title="Raio-X do Prato", page_icon="🍖", layout="wide")
garantir_banco()

st.title("Raio-X do Prato")
st.caption("A câmera enquadra apenas o prato, nunca o cliente (LGPD).")

df_itens = db.itens()
col_foto, col_res = st.columns(2)

with col_foto:
    origem_foto = st.radio("Origem da foto", ["Câmera", "Enviar arquivo"], horizontal=True)
    if origem_foto == "Câmera":
        foto = st.camera_input("Foto do prato na balança")
    else:
        foto = st.file_uploader("Foto do prato", type=["jpg", "jpeg", "png"])
    if foto is not None and origem_foto == "Enviar arquivo":
        st.image(foto, width="stretch")
    peso = st.number_input("Peso do prato (gramas)", min_value=0, max_value=3000, step=10, value=0)
    analisar = st.button("Analisar prato", type="primary", width="stretch")

with col_res:
    if analisar:
        if peso <= 0:
            st.warning("Informe o peso do prato.")
        elif foto is None:
            st.warning("Tire ou envie a foto do prato.")
        else:
            with st.spinner("Analisando o prato..."):
                composicao, origem, erro = analisar_prato(foto.getvalue(), foto.type, df_itens["nome"].tolist())
            df, resumo = calculos.calcular_prato(peso, composicao, df_itens, db.preco_kg())

            if df.empty:
                st.error("A IA não reconheceu nenhum item do buffet nesta foto. Tente outra foto.")
            else:
                db.salvar_prato(resumo, df, origem)
                if erro:
                    st.info(f"A IA não respondeu, então foi usado o modo demo. Detalhe: {erro}")
                st.markdown(f"**Origem da análise:** {'IA (Gemini)' if origem == 'ia' else 'modo demo'}")

                m1, m2, m3 = st.columns(3)
                m1.metric("Cliente paga", f"R$ {resumo['receita']:.2f}")
                m2.metric("Custo estimado", f"R$ {resumo['custo_estimado']:.2f}")
                m3.metric("Margem estimada", f"{resumo['margem'] * 100:.1f}%")

                st.dataframe(
                    df, hide_index=True, width="stretch",
                    column_config={
                        "item": "Item", "categoria": "Categoria",
                        "percentual": st.column_config.ProgressColumn("% do prato", format="%.1f%%",
                                                                      min_value=0, max_value=100),
                        "peso_g": st.column_config.NumberColumn("Peso (g)", format="%.0f"),
                        "custo": st.column_config.NumberColumn("Custo (R$)", format="R$ %.2f"),
                    })
                st.caption("Composição estimada a partir da foto. O painel do gerente mostra os totais.")
    else:
        st.info("Tire a foto, informe o peso e clique em **Analisar prato**.")
