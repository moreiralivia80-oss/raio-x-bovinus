"""Gera dados de DEMONSTRAÇÃO realistas para o painel (até existir dado real do salão).

Rodar:  python -m painel.simulador            (30 dias, apaga e recria o banco)
        python -m painel.simulador --dias 14

O que o modelo imita (hipóteses, ajustar com a Bovinu'S):
- almoço por quilo das 11h às 16h, pico entre 12h30 e 13h30, fim de semana mais cheio;
- grupos de 1 a 5 pessoas, cada pessoa com sua comanda; mesas dos 3 salões do mapa;
- fila: quanto mais gente entrou nos últimos 15 min, mais demora até a balança;
- limpeza: quanto mais mesas sujas ao mesmo tempo, mais demora; Salão Superior (escada) é mais lento;
- ~25% respondem a avaliação (incentivo de desconto/cashback); a nota de espera acompanha o tempo real.
"""
import argparse
import random
from datetime import datetime, timedelta

from . import banco
from .banco import FORMATO
from .eventos import classificar_tema

PRECO_KG = 89.90

# probabilidade de o item estar no 1º prato e "tamanho" relativo da porção
CARDAPIO = {
    "Arroz": (0.78, 1.0), "Feijão": (0.66, 0.9), "Salada verde": (0.55, 0.45), "Farofa": (0.42, 0.35),
    "Vinagrete": (0.36, 0.35), "Batata frita": (0.33, 0.6), "Maionese": (0.20, 0.5), "Tomate": (0.25, 0.3),
    "Mandioca": (0.09, 0.5), "Legumes": (0.08, 0.4), "Macarrão": (0.15, 0.7), "Estrogonofe": (0.16, 0.7),
    "Lasanha": (0.12, 0.9), "Picanha": (0.58, 1.05), "Fraldinha": (0.36, 0.9), "Costela": (0.20, 0.9),
    "Cupim": (0.12, 0.8), "Maminha": (0.15, 0.8), "Linguiça": (0.32, 0.5), "Frango": (0.20, 0.6),
    "Coração de frango": (0.15, 0.4), "Peixe": (0.05, 0.7),
}
MOTIVOS = ["Frio", "Sem sabor", "Seco", "Salgado demais", "Aparência ruim", "Outro"]
CRITICADOS = {"Lasanha": 0.30, "Peixe": 0.25, "Mandioca": 0.18, "Batata frita": 0.12, "Costela": 0.08}

COMENTARIOS = {
    "comida": ["Picanha no ponto, muito boa!", "Carne estava um pouco fria.", "Lasanha estava seca.",
               "Comida deliciosa, tempero ótimo.", "Faltou reposição de farofa.", "Arroz estava salgado.",
               "Buffet de saladas muito fresco."],
    "espera": ["Fila da churrasqueira muito demorada.", "Demorei para conseguir pesar o prato.",
               "Esperei bastante na fila do buffet.", "Rápido, quase sem fila."],
    "limpeza": ["A mesa estava suja quando cheguei.", "Demoraram para limpar a mesa ao lado.",
                "Salão limpo e organizado."],
    "atendimento": ["Garçom muito educado.", "Demoraram para trazer a bebida.", "Atendimento simpático."],
}


def _horario_chegada(rnd, dia):
    while True:  # mistura: pico do almoço + cauda da tarde
        minutos = rnd.gauss(12 * 60 + 55, 48) if rnd.random() < 0.82 else rnd.uniform(11 * 60, 15 * 60 + 30)
        if 11 * 60 <= minutos <= 15 * 60 + 40:
            return dia + timedelta(minutes=minutos)


def _montar_prato(rnd, itens_custo, peso_g, tipo):
    if tipo == "sobremesa":
        escolhidos = {rnd.choice(["Pudim", "Mousse"]): 1.0}
    else:
        escolhidos = {}
        for nome, (prob, porcao) in CARDAPIO.items():
            p = prob * (1.35 if tipo == "repeticao" and itens_custo[nome][0] == "carne" else 1)
            p = p * (0.5 if tipo == "repeticao" and itens_custo[nome][0] != "carne" else 1)
            if rnd.random() < p:
                escolhidos[nome] = porcao * rnd.uniform(0.6, 1.5)
        if not escolhidos:
            escolhidos = {"Arroz": 1.0, "Picanha": 1.0}
    total = sum(escolhidos.values())
    itens, custo = [], 0.0
    for nome, w in escolhidos.items():
        cat, custo_kg = itens_custo[nome]
        pct = w / total * 100
        peso_item = peso_g * pct / 100
        c = peso_item / 1000 * custo_kg
        custo += c
        itens.append((nome, cat, round(pct, 1), round(peso_item), round(c, 2), rnd.randint(62, 98)))
    return itens, round(custo, 2)


def limpar(con):
    """Apaga os registros do salão (mantém mesas e itens do buffet). Não faz commit."""
    for tabela in ("avaliacao_itens", "avaliacoes", "itens_prato", "pratos", "eventos_comanda",
                   "limpezas_mesa", "comandas", "meta"):
        con.execute(f"DELETE FROM {tabela}")
    con.execute("DELETE FROM sqlite_sequence")


def gerar(con, dias=30, semente=42, agora=None):
    rnd = random.Random(semente)
    agora = agora or datetime.now()
    agora_txt = agora.strftime(FORMATO)
    limpar(con)

    itens_custo = {r["nome"]: (r["categoria"], r["custo_kg"]) for r in con.execute("SELECT * FROM itens_buffet")}
    mesas = {s: [r[0] for r in con.execute("SELECT numero FROM mesas WHERE salao = ?", (s,))]
             for s in ("Inferior", "Principal", "Superior")}
    lentidao_salao = {"Inferior": 0.0, "Principal": 0.6, "Superior": 3.2}

    eventos, pratos_buf, limpezas, avaliacoes = [], [], [], []
    comanda_id = prato_id = avaliacao_id = 0
    codigo_cartao = 0
    hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)

    for d in range(dias - 1, -1, -1):
        dia = hoje - timedelta(days=d)
        fds = dia.weekday() >= 5
        n_clientes = int(rnd.gauss(390 if fds else 265, 25))
        # grupos de clientes
        grupos, n = [], 0
        while n < n_clientes:
            tam = rnd.choices([1, 2, 3, 4, 5], [22, 38, 18, 15, 7])[0]
            grupos.append((_horario_chegada(rnd, dia), tam))
            n += tam
        grupos.sort()
        chegadas = [g[0] for g in grupos for _ in range(g[1])]
        livre_em = {m: dia for s in mesas.values() for m in s}  # quando cada mesa fica livre de novo
        sujas_ate = []  # (saiu, limpa) para medir sobrecarga de limpeza

        for chegada, tam in grupos:
            # fila proporcional a quem chegou nos 15 min anteriores
            recentes = sum(1 for c in chegadas if chegada - timedelta(minutes=15) <= c <= chegada)
            salao = rnd.choices(list(mesas), [20, 45, 35])[0]
            candidatas = [m for m in mesas[salao] if livre_em[m] <= chegada] or \
                         [m for s in mesas.values() for m in s if livre_em[m] <= chegada]
            mesa = rnd.choice(candidatas) if candidatas else rnd.choice(mesas[salao])
            salao = next(s for s, ms in mesas.items() if mesa in ms)
            saidas = []
            for _ in range(tam):
                comanda_id += 1
                codigo_cartao = codigo_cartao % 500 + 1
                entrada = chegada + timedelta(seconds=rnd.randint(0, 90))
                min_pesar = max(2.0, rnd.lognormvariate(1.25, 0.25) + recentes * rnd.uniform(0.17, 0.25))
                balanca = entrada + timedelta(minutes=min_pesar)
                ev = [(comanda_id, "entrada", entrada, None, "Caixa entrada"),
                      (comanda_id, "balanca", balanca, None, "Balança")]
                pesagens = [(balanca, "primeiro")]
                if rnd.random() < 0.72:  # pediu bebida: garçom pipa a comanda na mesa
                    espera_garcom = rnd.uniform(1, 4) + recentes * rnd.uniform(0.02, 0.06)
                    ev.append((comanda_id, "atendimento_mesa", balanca + timedelta(minutes=espera_garcom), mesa,
                               "Garçom"))
                ultimo = balanca
                if rnd.random() < 0.27:
                    ultimo = balanca + timedelta(minutes=rnd.uniform(14, 26))
                    pesagens.append((ultimo, "repeticao"))
                if rnd.random() < 0.18:
                    ultimo = ultimo + timedelta(minutes=rnd.uniform(8, 15))
                    pesagens.append((ultimo, "sobremesa"))
                for momento, _ in pesagens[1:]:
                    ev.append((comanda_id, "balanca", momento, None, "Balança"))
                pagamento = ultimo + timedelta(minutes=rnd.uniform(14, 35))
                ev.append((comanda_id, "pagamento", pagamento, None, rnd.choice(["Caixa 1", "Caixa 2", "Caixa auxiliar"])))
                saidas.append(pagamento)

                comida_ruim = False
                itens_cliente = []
                for momento, tipo in pesagens:
                    if tipo == "sobremesa":
                        peso = rnd.uniform(90, 180)
                    else:
                        peso = min(1200, max(160, rnd.gauss(520 if tipo == "primeiro" else 330, 140)))
                    prato_id += 1
                    itens, custo = _montar_prato(rnd, itens_custo, peso, tipo)
                    pratos_buf.append(((prato_id, comanda_id, momento, round(peso), round(peso / 1000 * PRECO_KG, 2),
                                        custo, rnd.randint(60, 95), "simulado"), itens))
                    itens_cliente += [i[0] for i in itens]
                eventos.append((comanda_id, str(codigo_cartao), entrada, pagamento, mesa, ev))

                # avaliação (QR Code na mesa) ~25%
                if rnd.random() < 0.25:
                    avaliacao_id += 1
                    criticas = [i for i in set(itens_cliente) if rnd.random() < CRITICADOS.get(i, 0.02)]
                    comida_ruim = bool(criticas)
                    nota_comida = max(1, min(5, round(rnd.gauss(4.5 - 1.3 * comida_ruim, 0.6))))
                    nota_espera = max(1, min(5, round(rnd.gauss(5.9 - 0.28 * min_pesar, 0.7))))
                    nota_limpeza = max(1, min(5, round(rnd.gauss(4.7 - 0.3 * lentidao_salao[salao], 0.6))))
                    motivo = rnd.choice(MOTIVOS) if criticas else None
                    gostou = [i for i in set(itens_cliente) if i not in criticas and
                              rnd.random() < (0.55 if itens_custo[i][0] == "carne" else 0.12)][:2]
                    tema_base = None
                    if nota_espera <= 2:
                        tema_base = "espera"
                    elif comida_ruim:
                        tema_base = "comida"
                    elif rnd.random() < 0.3:
                        tema_base = rnd.choice(list(COMENTARIOS))
                    comentario = rnd.choice(COMENTARIOS[tema_base]) if tema_base and rnd.random() < 0.6 else None
                    avaliacoes.append((avaliacao_id, pagamento - timedelta(minutes=rnd.uniform(1, 6)), mesa, comanda_id,
                                       nota_comida, nota_espera, comentario, classificar_tema(comentario),
                                       rnd.choice(["desconto", "cashback"]), gostou, criticas,
                                       nota_limpeza, motivo))

            # mesa fica suja quando o último do grupo paga
            saiu = max(saidas) + timedelta(minutes=rnd.uniform(0, 2))
            sobrecarga = sum(1 for s, l in sujas_ate if s <= saiu < l)
            min_suja = max(1.0, rnd.lognormvariate(1.05, 0.35) + lentidao_salao[salao] + sobrecarga * rnd.uniform(0.55, 0.85))
            limpa = saiu + timedelta(minutes=min_suja)
            sujas_ate.append((saiu, limpa))
            livre_em[mesa] = limpa
            limpezas.append((mesa, saiu, limpa, "caixa" if rnd.random() < 0.6 else "garcom"))

    # ----- grava só o que já aconteceu até "agora" -----
    def t(dt):
        return dt.strftime(FORMATO)

    for cid, codigo, entrada, pagamento, mesa, ev in eventos:
        if entrada > agora:
            continue
        con.execute("INSERT INTO comandas (id, codigo, aberta_em, fechada_em, mesa_numero) VALUES (?, ?, ?, ?, ?)",
                    (cid, codigo, t(entrada), t(pagamento) if pagamento <= agora else None, mesa))
        con.executemany("INSERT INTO eventos_comanda (comanda_id, tipo, momento, mesa_numero, ponto) VALUES (?, ?, ?, ?, ?)",
                        [(c, tipo, t(m), me, p) for c, tipo, m, me, p in ev if m <= agora])
    for (pid, cid, momento, peso, receita, custo, precisao, origem), itens in pratos_buf:
        if momento > agora:
            continue
        con.execute("""INSERT INTO pratos (id, comanda_id, pesado_em, peso_g, receita, custo_estimado,
                                           precisao, origem) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (pid, cid, t(momento), peso, receita, custo, precisao, origem))
        con.executemany("""INSERT INTO itens_prato (prato_id, item, categoria, percentual, peso_g, custo, confianca)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""", [(pid, *i) for i in itens])
    for mesa, saiu, limpa, origem in limpezas:
        if saiu <= agora:
            con.execute("""INSERT INTO limpezas_mesa (mesa_numero, saiu_em, limpa_em, origem, limpa_origem)
                           VALUES (?, ?, ?, ?, ?)""",
                        (mesa, t(saiu), t(limpa) if limpa <= agora else None, origem,
                         "garcom" if limpa <= agora else None))
    for aid, criada, mesa, cid, nc, ne, com, tema, ben, gostou, criticas, nl, motivo in avaliacoes:
        if criada > agora:
            continue
        con.execute("""INSERT INTO avaliacoes (id, criada_em, mesa_numero, comanda_id, nota_comida, nota_espera,
                                               comentario, tema, beneficio, nota_limpeza, motivo, origem)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'simulado')""",
                    (aid, t(criada), mesa, cid, nc, ne, com, tema, ben, nl, motivo))
        con.executemany("INSERT INTO avaliacao_itens VALUES (?, ?, ?)",
                        [(aid, i, "gostou") for i in gostou] + [(aid, i, "nao_gostou") for i in criticas])

    # Fora do horário do almoço o salão estaria vazio; deixa algumas mesas sujas para a demonstração.
    if not con.execute("SELECT 1 FROM limpezas_mesa WHERE limpa_em IS NULL").fetchone():
        for mesa in rnd.sample(range(1, 91), 7):
            con.execute("INSERT INTO limpezas_mesa (mesa_numero, saiu_em, origem) VALUES (?, ?, 'garcom')",
                        (mesa, t(agora - timedelta(minutes=rnd.choice([2, 4, 6, 9, 13, 17, 24])))))
    con.execute("INSERT OR REPLACE INTO meta VALUES ('dados_simulados', '1')")
    con.execute("INSERT OR REPLACE INTO meta VALUES ('simulado_em', ?)", (agora_txt,))
    con.commit()


def main():
    parser = argparse.ArgumentParser(description="Gera dados de demonstração para o painel.")
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args()
    con = banco.conectar()
    banco.criar_tabelas(con)
    gerar(con, args.dias, args.semente)
    total = con.execute("SELECT COUNT(*) FROM comandas").fetchone()[0]
    print(f"Dados de demonstração gerados: {total} comandas em {args.dias} dias -> {banco.caminho_banco()}")


if __name__ == "__main__":
    main()
