"""Cria o banco com itens de exemplo e gera dados SIMULADOS para o painel.

ATENÇÃO: custos, preço de venda e histórico são FICTÍCIOS, só para demonstração.
Troque pelos valores reais quando a Bovinu'S fornecer.

Uso (na pasta do projeto):  python -m core.seed
"""
import random
from datetime import datetime, timedelta

from core import calculos, db
from core.ia import composicao_demo

PRECO_KG_VENDA = 89.90  # FICTÍCIO

ITENS = [  # nome, categoria, custo R$/kg (FICTÍCIO)
    ("Picanha", "carne", 75.0), ("Fraldinha", "carne", 48.0), ("Costela", "carne", 38.0),
    ("Linguiça", "carne", 24.0), ("Frango", "carne", 18.0), ("Cupim", "carne", 42.0),
    ("Arroz", "acompanhamento", 6.0), ("Feijão", "acompanhamento", 8.0),
    ("Farofa", "acompanhamento", 9.0), ("Batata frita", "acompanhamento", 14.0),
    ("Salada verde", "salada", 10.0), ("Vinagrete", "salada", 9.0), ("Maionese", "salada", 12.0),
    ("Estrogonofe", "quente", 22.0), ("Lasanha", "quente", 20.0), ("Mandioca", "quente", 7.0),
    ("Pudim", "sobremesa", 16.0), ("Mousse", "sobremesa", 14.0),
]

COMENTARIOS = ["Carne estava ótima", "Demorou na fila da churrasqueira", "Mesa estava suja quando cheguei",
               "Estrogonofe estava frio", "Garçom muito educado", "Tudo excelente", "Arroz meio seco", ""]


def criar_base():
    if db.DB_PATH.exists():
        db.DB_PATH.unlink()
    db.criar_tabelas()
    with db.conectar() as conn:
        conn.executemany("INSERT INTO itens (nome, categoria, custo_kg) VALUES (?,?,?)", ITENS)
        conn.execute("INSERT INTO config VALUES ('preco_kg_venda', ?)", (str(PRECO_KG_VENDA),))


def simular(dias=5, seed=42):
    rnd = random.Random(seed)
    df_itens = db.itens()
    nomes = df_itens["nome"].tolist()
    hoje = datetime.now().replace(minute=0, second=0, microsecond=0)
    conn = db.conectar()

    for d in range(dias, 0, -1):
        dia = hoje - timedelta(days=d)
        for hora, fluxo in [(11, 20), (12, 55), (13, 45), (14, 20), (15, 8)]:
            for _ in range(int(fluxo * rnd.uniform(0.8, 1.2))):
                momento = dia.replace(hour=hora, minute=rnd.randint(0, 59), second=rnd.randint(0, 59))
                # prato
                comp = composicao_demo(rnd.randbytes(8), nomes)
                df, resumo = calculos.calcular_prato(max(rnd.gauss(520, 110), 180), comp, df_itens, PRECO_KG_VENDA)
                db.salvar_prato(resumo, df, "simulado", momento.isoformat(), conn)
                # mesa: cliente sai ~40 min depois; no pico a limpeza demora mais, e mais no salão superior
                mesa = rnd.randint(1, 90)
                saiu = momento + timedelta(minutes=rnd.randint(25, 55))
                espera = rnd.uniform(2, 6) * (1.8 if hora in (12, 13) else 1) * (1.5 if mesa > 50 else 1)
                db.registrar_evento_mesa(mesa, "saiu", saiu.isoformat(), conn)
                db.registrar_evento_mesa(mesa, "limpa", (saiu + timedelta(minutes=espera)).isoformat(timespec="seconds"), conn)
                # avaliação: ~1 em cada 5 clientes responde
                if rnd.random() < 0.2:
                    nota_espera = rnd.choice([2, 3, 3, 4] if hora in (12, 13) else [3, 4, 5, 5])
                    gostou = rnd.sample(nomes, k=rnd.randint(0, 2))
                    ruins = [i for i in rnd.sample(["Estrogonofe", "Arroz", "Lasanha", "Costela"], k=1)
                             if rnd.random() < 0.35]
                    comentario = rnd.choice(COMENTARIOS)
                    from core.ia import PALAVRAS  # noqa: classificação offline para os dados simulados
                    assunto = next((a for a, ps in PALAVRAS.items() if any(p in comentario.lower() for p in ps)),
                                   "outro") if comentario else None
                    db.salvar_avaliacao(mesa, rnd.choice([3, 4, 4, 5, 5]) - (1 if ruins else 0), nota_espera,
                                        gostou, ruins, comentario, assunto,
                                        (saiu - timedelta(minutes=2)).isoformat(), conn)
    conn.commit()
    conn.close()


def garantir_banco():
    """Chamado pelo app: cria o banco com dados de demonstração se ainda não existir."""
    if db.banco_vazio():
        criar_base()
        simular()


if __name__ == "__main__":
    criar_base()
    simular()
    print(f"Banco criado em {db.DB_PATH}")
