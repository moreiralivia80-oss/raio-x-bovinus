"""Módulo 3: Controle das mesas (tela do garçom).

Toque na mesa:
  - mesa livre  → "cliente saiu" (fica suja, vermelha)
  - mesa suja   → "limpa" (volta a ficar livre)
"""
from datetime import datetime

import streamlit as st

from core import calculos, db
from core.seed import garantir_banco

st.set_page_config(page_title="Controle das mesas", page_icon="🍖", layout="wide")
garantir_banco()

st.title("Controle das mesas")
st.caption("Toque na mesa quando o cliente sair. Toque de novo quando ela estiver limpa.")

status = calculos.status_mesas()
agora = datetime.now()
sujas = {m: s for m, s in status.items() if s["suja"]}

c1, c2, c3 = st.columns(3)
c1.metric("Mesas sujas agora", len(sujas))
atrasadas = [m for m, s in sujas.items() if (agora - s["desde"]).total_seconds() > 5 * 60]
c2.metric("Sujas há mais de 5 min", len(atrasadas))
c3.metric("Mesas livres", len(status) - len(sujas))

POR_LINHA = 10
for salao, faixa in db.SALOES.items():
    st.subheader(salao)
    mesas = list(faixa)
    for inicio in range(0, len(mesas), POR_LINHA):
        cols = st.columns(POR_LINHA)
        for col, mesa in zip(cols, mesas[inicio:inicio + POR_LINHA]):
            s = status[mesa]
            if s["suja"]:
                minutos = int((agora - s["desde"]).total_seconds() // 60)
                rotulo, tipo, evento = f"{mesa} · suja {minutos}min", "primary", "limpa"
            else:
                rotulo, tipo, evento = f"{mesa}", "secondary", "saiu"
            if col.button(rotulo, key=f"mesa_{mesa}", type=tipo, width="stretch"):
                db.registrar_evento_mesa(mesa, evento)
                st.rerun()

st.button("Atualizar", help="Recarrega o status das mesas")
