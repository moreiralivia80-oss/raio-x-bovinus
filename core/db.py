"""Banco de dados SQLite + leitura com pandas."""
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
DB_PATH = RAIZ / "data" / "bovinus.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS itens (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT NOT NULL UNIQUE,
    categoria TEXT NOT NULL,      -- carne, acompanhamento, salada, quente, sobremesa
    custo_kg  REAL NOT NULL       -- R$ por kg
);
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
-- Módulo 1: Raio-X do Prato
CREATE TABLE IF NOT EXISTS pratos (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    momento        TEXT NOT NULL,
    peso_g         REAL NOT NULL,
    origem         TEXT NOT NULL, -- ia, demo, simulado
    receita        REAL NOT NULL,
    custo_estimado REAL NOT NULL,
    margem         REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS prato_itens (
    prato_id   INTEGER NOT NULL REFERENCES pratos(id),
    item       TEXT NOT NULL,
    categoria  TEXT NOT NULL,
    percentual REAL NOT NULL,
    peso_g     REAL NOT NULL,
    custo      REAL NOT NULL
);
-- Módulo 2: Avaliação do cliente
CREATE TABLE IF NOT EXISTS avaliacoes (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    momento       TEXT NOT NULL,
    mesa          INTEGER,
    nota_comida   INTEGER NOT NULL,  -- 1 a 5
    nota_espera   INTEGER NOT NULL,  -- 1 a 5
    comentario    TEXT,
    assunto       TEXT               -- classificado pela IA: comida, espera, limpeza, atendimento, outro
);
CREATE TABLE IF NOT EXISTS avaliacao_itens (
    avaliacao_id INTEGER NOT NULL REFERENCES avaliacoes(id),
    item         TEXT NOT NULL,
    tipo         TEXT NOT NULL       -- gostou | nao_gostou
);
-- Módulo 3: Controle das mesas
CREATE TABLE IF NOT EXISTS mesa_eventos (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa    INTEGER NOT NULL,
    tipo    TEXT NOT NULL,           -- saiu (mesa fica suja) | limpa
    momento TEXT NOT NULL
);
"""

# Mapa da casa apresentado pela Bovinu'S (quantidades aproximadas)
SALOES = {"Salão Inferior": range(1, 21), "Salão Principal": range(21, 51), "Salão Superior": range(51, 91)}


def salao_da_mesa(mesa):
    for nome, faixa in SALOES.items():
        if mesa in faixa:
            return nome
    return "Outro"


def agora():
    return datetime.now().isoformat(timespec="seconds")


def conectar():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def criar_tabelas():
    with conectar() as conn:
        conn.executescript(SCHEMA)


def banco_vazio():
    if not DB_PATH.exists():
        return True
    with conectar() as conn:
        tem = conn.execute("SELECT name FROM sqlite_master WHERE name='itens'").fetchone()
        return not tem or conn.execute("SELECT COUNT(*) FROM itens").fetchone()[0] == 0


def ler(sql, params=()):
    """Executa um SELECT e devolve um DataFrame do pandas."""
    with conectar() as conn:
        return pd.read_sql_query(sql, conn, params=params)


def itens():
    return ler("SELECT * FROM itens ORDER BY categoria, nome")


def preco_kg():
    df = ler("SELECT valor FROM config WHERE chave = 'preco_kg_venda'")
    return float(df.iloc[0, 0]) if len(df) else 0.0


# ---------- gravação ----------

def salvar_prato(resultado, df_itens, origem, momento=None, conn=None):
    proprio = conn is None
    conn = conn or conectar()
    cur = conn.execute(
        "INSERT INTO pratos (momento, peso_g, origem, receita, custo_estimado, margem) VALUES (?,?,?,?,?,?)",
        (momento or agora(), resultado["peso_g"], origem, resultado["receita"],
         resultado["custo_estimado"], resultado["margem"]))
    pid = cur.lastrowid
    conn.executemany(
        "INSERT INTO prato_itens (prato_id, item, categoria, percentual, peso_g, custo) VALUES (?,?,?,?,?,?)",
        [(pid, r.item, r.categoria, r.percentual, r.peso_g, r.custo) for r in df_itens.itertuples()])
    if proprio:
        conn.commit()
        conn.close()
    return pid


def salvar_avaliacao(mesa, nota_comida, nota_espera, gostou, nao_gostou, comentario, assunto,
                     momento=None, conn=None):
    proprio = conn is None
    conn = conn or conectar()
    cur = conn.execute(
        "INSERT INTO avaliacoes (momento, mesa, nota_comida, nota_espera, comentario, assunto) VALUES (?,?,?,?,?,?)",
        (momento or agora(), mesa, nota_comida, nota_espera, comentario or None, assunto))
    aid = cur.lastrowid
    linhas = [(aid, i, "gostou") for i in gostou] + [(aid, i, "nao_gostou") for i in nao_gostou]
    conn.executemany("INSERT INTO avaliacao_itens (avaliacao_id, item, tipo) VALUES (?,?,?)", linhas)
    if proprio:
        conn.commit()
        conn.close()
    return aid


def registrar_evento_mesa(mesa, tipo, momento=None, conn=None):
    proprio = conn is None
    conn = conn or conectar()
    conn.execute("INSERT INTO mesa_eventos (mesa, tipo, momento) VALUES (?,?,?)", (mesa, tipo, momento or agora()))
    if proprio:
        conn.commit()
        conn.close()
