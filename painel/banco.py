"""Conexão com o SQLite e criação das tabelas.

O arquivo do banco fica em dados/bovinus.db (ou no caminho da variável BOVINUS_DB).
No executável (.exe), a pasta dados/ fica ao lado do PainelBovinus.exe.
"""
import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

PASTA = Path(__file__).resolve().parent  # no .exe aponta para a pasta temporária com schema.sql
RAIZ = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PASTA.parent
CAMINHO_PADRAO = RAIZ / "dados" / "bovinus.db"
FORMATO = "%Y-%m-%d %H:%M:%S"

# Mesas conforme o mapa da casa (números sugeridos; ajuste à numeração real)
SALOES = {"Inferior": range(1, 21), "Principal": range(21, 51), "Superior": range(51, 91)}

# Mesmos itens e custos FICTÍCIOS do Raio-X (servicos/custos.py). Troque pelos reais.
ITENS_INICIAIS = {
    "Picanha": ("carne", 75.0), "Fraldinha": ("carne", 48.0), "Costela": ("carne", 38.0),
    "Cupim": ("carne", 42.0), "Maminha": ("carne", 45.0), "Linguiça": ("carne", 24.0),
    "Frango": ("carne", 18.0), "Coração de frango": ("carne", 22.0), "Peixe": ("carne", 40.0),
    "Arroz": ("acompanhamento", 6.0), "Feijão": ("acompanhamento", 8.0),
    "Farofa": ("acompanhamento", 9.0), "Batata frita": ("acompanhamento", 14.0),
    "Mandioca": ("acompanhamento", 7.0), "Macarrão": ("acompanhamento", 8.0),
    "Salada verde": ("salada", 10.0), "Tomate": ("salada", 8.0), "Vinagrete": ("salada", 9.0),
    "Maionese": ("salada", 12.0), "Legumes": ("salada", 9.0),
    "Estrogonofe": ("quente", 22.0), "Lasanha": ("quente", 20.0),
    "Pudim": ("sobremesa", 16.0), "Mousse": ("sobremesa", 14.0),
}


def caminho_banco():
    return Path(os.environ.get("BOVINUS_DB", CAMINHO_PADRAO))


def pasta_fotos():
    """Fotos dos pratos ficam ao lado do banco, em dados/fotos/ (fora do GitHub)."""
    pasta = caminho_banco().parent / "fotos"
    pasta.mkdir(parents=True, exist_ok=True)
    return pasta


def conectar(caminho=None):
    caminho = Path(caminho or caminho_banco())
    caminho.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(caminho, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")  # leitura do painel não trava quem grava
    return con


# Colunas acrescentadas depois da 1ª versão: bancos antigos ganham as colunas sem perder dados
COLUNAS_NOVAS = [
    ("eventos_comanda", "id_cliente", "TEXT"),
    ("limpezas_mesa", "limpa_origem", "TEXT"),
    ("avaliacoes", "nota_limpeza", "INTEGER CHECK (nota_limpeza BETWEEN 1 AND 5)"),
    ("avaliacoes", "motivo", "TEXT"),
    ("avaliacoes", "origem", "TEXT"),
    ("avaliacoes", "chave_origem", "TEXT"),
    ("pratos", "foto", "TEXT"),
]


def _migrar(con):
    for tabela, coluna, tipo in COLUNAS_NOVAS:
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabela})")}
        if existentes and coluna not in existentes:
            con.execute(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")


def criar_tabelas(con):
    _migrar(con)
    con.executescript((PASTA / "schema.sql").read_text(encoding="utf-8"))
    if not con.execute("SELECT 1 FROM mesas LIMIT 1").fetchone():
        con.executemany(
            "INSERT INTO mesas (numero, salao) VALUES (?, ?)",
            [(n, salao) for salao, numeros in SALOES.items() for n in numeros],
        )
    if not con.execute("SELECT 1 FROM itens_buffet LIMIT 1").fetchone():
        con.executemany(
            "INSERT INTO itens_buffet (nome, categoria, custo_kg) VALUES (?, ?, ?)",
            [(nome, cat, custo) for nome, (cat, custo) in ITENS_INICIAIS.items()],
        )
    con.commit()


def agora():
    return datetime.now().strftime(FORMATO)


def texto_data(valor):
    """Aceita datetime ou texto e devolve 'AAAA-MM-DD HH:MM:SS'."""
    if valor is None:
        return agora()
    if isinstance(valor, datetime):
        return valor.strftime(FORMATO)
    return datetime.fromisoformat(str(valor).replace("T", " ").replace("Z", "")).strftime(FORMATO)
