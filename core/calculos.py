"""Regras de negócio e análises com pandas."""
from datetime import datetime

import pandas as pd

from core import db


# ---------- Módulo 1: Raio-X do Prato ----------

def calcular_prato(peso_g, composicao, df_itens, preco_kg):
    """composicao = {nome_item: percentual}. Devolve (DataFrame por item, resumo do prato)."""
    comp = pd.DataFrame(list(composicao.items()), columns=["item", "percentual"])
    comp["chave"] = comp["item"].str.lower().str.strip()
    base = df_itens.assign(chave=df_itens["nome"].str.lower().str.strip())

    df = comp.merge(base[["chave", "nome", "categoria", "custo_kg"]], on="chave", how="inner")
    df = df[df["percentual"] > 0].copy()
    if df.empty:
        df = pd.DataFrame(columns=["item", "categoria", "percentual", "peso_g", "custo"])
        custo = 0.0
    else:
        df["percentual"] = df["percentual"] / df["percentual"].sum() * 100   # normaliza para 100%
        df["peso_g"] = peso_g * df["percentual"] / 100
        df["custo"] = df["peso_g"] / 1000 * df["custo_kg"]
        df = df.rename(columns={"item": "_ia", "nome": "item"})
        df = df[["item", "categoria", "percentual", "peso_g", "custo"]].round(2)
        df = df.sort_values("percentual", ascending=False).reset_index(drop=True)
        custo = float(df["custo"].sum())

    receita = peso_g / 1000 * preco_kg
    resumo = {
        "peso_g": peso_g,
        "receita": round(receita, 2),
        "custo_estimado": round(custo, 2),
        "margem": round((receita - custo) / receita, 4) if receita else 0.0,
    }
    return df, resumo


def pratos_periodo(dia=None):
    filtro, params = ("WHERE date(momento) = ?", (dia,)) if dia else ("", ())
    return db.ler(f"SELECT * FROM pratos {filtro}", params)


def itens_periodo(dia=None):
    filtro, params = ("WHERE date(p.momento) = ?", (dia,)) if dia else ("", ())
    return db.ler(f"""SELECT pi.*, p.momento FROM prato_itens pi
                      JOIN pratos p ON p.id = pi.prato_id {filtro}""", params)


def mix_por_categoria(df_itens_servidos):
    """% do peso servido x % do custo, por categoria."""
    if df_itens_servidos.empty:
        return pd.DataFrame(columns=["% do peso", "% do custo"])
    g = df_itens_servidos.groupby("categoria")[["peso_g", "custo"]].sum()
    out = pd.DataFrame({
        "% do peso": g["peso_g"] / g["peso_g"].sum() * 100,
        "% do custo": g["custo"] / g["custo"].sum() * 100,
    }).round(1)
    return out.sort_values("% do custo", ascending=False)


def itens_que_mais_custam(df_itens_servidos, n=10):
    if df_itens_servidos.empty:
        return pd.DataFrame(columns=["item", "categoria", "peso_kg", "custo"])
    g = (df_itens_servidos.groupby(["item", "categoria"])
         .agg(peso_kg=("peso_g", lambda s: s.sum() / 1000), custo=("custo", "sum"))
         .reset_index().sort_values("custo", ascending=False).head(n))
    return g.round(2)


# ---------- Módulo 2: Avaliação ----------

def avaliacoes_periodo(dia=None):
    filtro, params = ("WHERE date(momento) = ?", (dia,)) if dia else ("", ())
    return db.ler(f"SELECT * FROM avaliacoes {filtro}", params)


def ranking_itens_avaliados(dia=None):
    """Quantas vezes cada item foi elogiado e criticado."""
    filtro, params = ("WHERE date(a.momento) = ?", (dia,)) if dia else ("", ())
    df = db.ler(f"""SELECT ai.item, ai.tipo FROM avaliacao_itens ai
                    JOIN avaliacoes a ON a.id = ai.avaliacao_id {filtro}""", params)
    if df.empty:
        return pd.DataFrame(columns=["item", "elogios", "criticas"])
    t = pd.crosstab(df["item"], df["tipo"])
    for col in ("gostou", "nao_gostou"):
        if col not in t:
            t[col] = 0
    t = t.rename(columns={"gostou": "elogios", "nao_gostou": "criticas"})[["elogios", "criticas"]]
    return t.reset_index().sort_values(["criticas", "elogios"], ascending=[False, True])


# ---------- Módulo 3: Mesas ----------

def status_mesas():
    """Status atual de cada mesa (último evento) e há quantos minutos está suja."""
    ev = db.ler("""SELECT mesa, tipo, momento FROM mesa_eventos
                   WHERE id IN (SELECT MAX(id) FROM mesa_eventos GROUP BY mesa)""")
    status = {m: {"suja": False, "desde": None} for faixa in db.SALOES.values() for m in faixa}
    for r in ev.itertuples():
        if r.mesa in status and r.tipo == "saiu":
            status[r.mesa] = {"suja": True, "desde": datetime.fromisoformat(r.momento)}
    return status


def tempos_limpeza(dia=None):
    """Para cada 'saiu', encontra o próximo 'limpa' da mesma mesa e calcula os minutos."""
    ev = db.ler("SELECT mesa, tipo, momento FROM mesa_eventos ORDER BY mesa, momento, id")
    if ev.empty:
        return pd.DataFrame(columns=["mesa", "salao", "saiu", "limpa", "minutos", "hora"])
    ev["momento"] = pd.to_datetime(ev["momento"], format="ISO8601")
    ev["proximo_tipo"] = ev.groupby("mesa")["tipo"].shift(-1)
    ev["proximo_momento"] = ev.groupby("mesa")["momento"].shift(-1)
    df = ev[(ev["tipo"] == "saiu") & (ev["proximo_tipo"] == "limpa")].copy()
    df = df.rename(columns={"momento": "saiu", "proximo_momento": "limpa"})
    df["minutos"] = (df["limpa"] - df["saiu"]).dt.total_seconds() / 60
    df["salao"] = df["mesa"].map(db.salao_da_mesa)
    df["hora"] = df["saiu"].dt.hour
    if dia:
        df = df[df["saiu"].dt.strftime("%Y-%m-%d") == dia]
    return df[["mesa", "salao", "saiu", "limpa", "minutos", "hora"]].round({"minutos": 1})


def dias_com_dados():
    df = db.ler("""SELECT DISTINCT date(momento) AS dia FROM pratos
                   UNION SELECT DISTINCT date(momento) FROM avaliacoes
                   UNION SELECT DISTINCT date(momento) FROM mesa_eventos ORDER BY dia DESC""")
    return df["dia"].dropna().tolist()
