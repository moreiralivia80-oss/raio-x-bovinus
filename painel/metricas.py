"""Cálculo de todos os números do painel do gerente.

Uma única função pública, montar_painel(), devolve um dicionário pronto para virar
JSON. Os números vêm das VIEWS do schema.sql; aqui só filtramos o período,
agrupamos e escrevemos os alertas automáticos.
"""
from datetime import datetime, timedelta

from . import planilha
from .banco import FORMATO

NOMES_TEMA = {"comida": "Comida", "espera": "Espera", "limpeza": "Limpeza",
              "atendimento": "Atendimento", "outro": "Outros"}


# ------------------------------------------------------------------ apoio

def _media(valores):
    valores = [v for v in valores if v is not None]
    return round(sum(valores) / len(valores), 1) if valores else None


def _percentil(valores, p):
    valores = sorted(v for v in valores if v is not None)
    if not valores:
        return None
    k = (len(valores) - 1) * p / 100
    baixo, alto = int(k), min(int(k) + 1, len(valores) - 1)
    return round(valores[baixo] + (valores[alto] - valores[baixo]) * (k - baixo), 1)


def _janela(dias, agora):
    """Período atual [ini, fim) e o período anterior do mesmo tamanho."""
    hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)
    ini = hoje - timedelta(days=dias - 1)
    fim = hoje + timedelta(days=1)
    anterior = ini - timedelta(days=dias)
    return [d.strftime(FORMATO) for d in (anterior, ini, fim)]


def _fmt_min(v):
    return f"{v:.1f}".replace(".", ",") + " min" if v is not None else "–"


def _fmt_pct(v, casas=0):
    return f"{v * 100:.{casas}f}".replace(".", ",") + "%"


# ------------------------------------------------------------------ blocos

def _resumo(con, ini, fim):
    """Números do topo do painel para um período."""
    p = con.execute(
        """SELECT COUNT(*) AS pratos, AVG(peso_g) AS peso, AVG(receita) AS receita,
                  AVG(custo_estimado) AS custo, SUM(receita) AS receita_total,
                  SUM(custo_estimado) AS custo_total, SUM(peso_g) AS peso_total
           FROM pratos WHERE pesado_em >= ? AND pesado_em < ?""", (ini, fim)).fetchone()
    jornada = con.execute(
        """SELECT min_ate_pesar, min_ate_atendimento_mesa, min_permanencia
           FROM vw_jornada_cliente WHERE entrada >= ? AND entrada < ?""", (ini, fim)).fetchall()
    clientes = con.execute(
        "SELECT COUNT(*) FROM comandas WHERE aberta_em >= ? AND aberta_em < ?", (ini, fim)).fetchone()[0]
    sujas = [r[0] for r in con.execute(
        "SELECT min_suja FROM vw_tempo_mesa_suja WHERE saiu_em >= ? AND saiu_em < ? AND conta_na_media = 1",
        (ini, fim))]
    fora_media = con.execute(
        """SELECT COUNT(*) FROM vw_tempo_mesa_suja WHERE saiu_em >= ? AND saiu_em < ?
           AND limpa_em IS NOT NULL AND conta_na_media = 0""", (ini, fim)).fetchone()[0]
    av = con.execute(
        """SELECT COUNT(*) AS n, AVG(nota_comida) AS comida, AVG(nota_espera) AS espera,
                  AVG(nota_limpeza) AS limpeza
           FROM avaliacoes WHERE criada_em >= ? AND criada_em < ?""", (ini, fim)).fetchone()

    pesar = [r["min_ate_pesar"] for r in jornada]
    return {
        "clientes": clientes,
        "pratos": p["pratos"],
        "peso_medio_g": round(p["peso"]) if p["peso"] else None,
        "receita_media": round(p["receita"], 2) if p["receita"] else None,
        "custo_medio": round(p["custo"], 2) if p["custo"] else None,
        "margem": round((p["receita_total"] - p["custo_total"]) / p["receita_total"], 4) if p["receita_total"] else None,
        "custo_kg": round(p["custo_total"] / p["peso_total"] * 1000, 2) if p["peso_total"] else None,
        "min_ate_pesar": _media(pesar),
        "min_ate_pesar_p90": _percentil(pesar, 90),
        "min_atendimento_mesa": _media([r["min_ate_atendimento_mesa"] for r in jornada]),
        "min_permanencia": _media([r["min_permanencia"] for r in jornada]),
        "min_mesa_suja": _media(sujas),
        "min_mesa_suja_p90": _percentil(sujas, 90),
        "limpezas": len(sujas),
        "limpezas_fora_da_media": fora_media,
        "avaliacoes": av["n"],
        "nota_comida": round(av["comida"], 2) if av["comida"] else None,
        "nota_espera": round(av["espera"], 2) if av["espera"] else None,
        "nota_limpeza": round(av["limpeza"], 2) if av["limpeza"] else None,
        "taxa_resposta": round(av["n"] / clientes, 4) if clientes else None,
    }


def _mix_itens(con, ini, fim):
    linhas = con.execute(
        """SELECT item, categoria, SUM(peso_g) AS peso, SUM(custo) AS custo, COUNT(DISTINCT prato_id) AS pratos
           FROM vw_mix_itens WHERE pesado_em >= ? AND pesado_em < ?
           GROUP BY item, categoria""", (ini, fim)).fetchall()
    total_pratos = con.execute(
        "SELECT COUNT(*) FROM pratos WHERE pesado_em >= ? AND pesado_em < ?", (ini, fim)).fetchone()[0] or 1
    peso_total = sum(r["peso"] for r in linhas) or 1
    custo_total = sum(r["custo"] for r in linhas) or 1
    itens = [{
        "item": r["item"], "categoria": r["categoria"],
        "pct_peso": round(r["peso"] / peso_total, 4),
        "pct_custo": round(r["custo"] / custo_total, 4),
        "custo_total": round(r["custo"], 2),
        "peso_kg": round(r["peso"] / 1000, 1),
        "pct_pratos": round(r["pratos"] / total_pratos, 4),
    } for r in linhas]
    return sorted(itens, key=lambda x: x["pct_custo"], reverse=True)


def _raio_x(con, ini, fim):
    """Pratos registrados pelo Raio-X: números, produtos mais consumidos e últimos pratos."""
    r = con.execute(
        """SELECT COUNT(*) AS pratos, AVG(peso_g) AS peso_medio, AVG(custo_estimado) AS custo_medio,
                  AVG(precisao) AS precisao_media, SUM(foto IS NOT NULL) AS com_foto,
                  SUM(origem = 'ia') AS pela_ia
           FROM pratos WHERE pesado_em >= ? AND pesado_em < ?""", (ini, fim)).fetchone()
    total = r["pratos"] or 0
    produtos = con.execute(
        """SELECT ip.item, ip.categoria, COUNT(DISTINCT ip.prato_id) AS pratos,
                  SUM(ip.peso_g) AS peso, SUM(ip.custo) AS custo, AVG(ip.confianca) AS confianca
           FROM itens_prato ip JOIN pratos p ON p.id = ip.prato_id
           WHERE p.pesado_em >= ? AND p.pesado_em < ?
           GROUP BY ip.item, ip.categoria
           ORDER BY pratos DESC, peso DESC LIMIT 12""", (ini, fim)).fetchall()
    ultimos = con.execute(
        """SELECT id, pesado_em, peso_g, receita, custo_estimado, precisao, origem, foto
           FROM pratos WHERE pesado_em >= ? AND pesado_em < ?
           ORDER BY pesado_em DESC, id DESC LIMIT 8""", (ini, fim)).fetchall()
    itens_por_prato = {}
    if ultimos:
        marcas = ",".join("?" * len(ultimos))
        for i in con.execute(
                f"""SELECT prato_id, item, percentual, confianca FROM itens_prato
                    WHERE prato_id IN ({marcas}) ORDER BY percentual DESC""", [u["id"] for u in ultimos]):
            itens_por_prato.setdefault(i["prato_id"], []).append(
                {"item": i["item"], "percentual": round(i["percentual"], 1), "confianca": i["confianca"]})
    return {
        "pratos": total,
        "pela_ia": r["pela_ia"] or 0,
        "com_foto": r["com_foto"] or 0,
        "peso_medio_g": round(r["peso_medio"]) if r["peso_medio"] else None,
        "custo_medio": _r2(r["custo_medio"]),
        "precisao_media": round(r["precisao_media"]) if r["precisao_media"] is not None else None,
        "mais_consumidos": [{
            "item": p["item"], "categoria": p["categoria"], "pratos": p["pratos"],
            "pct_pratos": round(p["pratos"] / total, 4) if total else 0,
            "peso_kg": round(p["peso"] / 1000, 2), "custo_total": round(p["custo"], 2),
            "confianca_media": round(p["confianca"]) if p["confianca"] is not None else None,
        } for p in produtos],
        "ultimos": [{
            "id": u["id"], "pesado_em": u["pesado_em"], "peso_g": round(u["peso_g"]),
            "receita": round(u["receita"], 2), "custo": round(u["custo_estimado"], 2),
            "precisao": u["precisao"], "origem": u["origem"], "tem_foto": bool(u["foto"]),
            "itens": itens_por_prato.get(u["id"], []),
        } for u in ultimos],
    }


def _por_hora(con, ini, fim):
    horas = {h: {"hora": h, "clientes": 0, "pesar": [], "suja": [], "receita": 0.0, "custo": 0.0}
             for h in range(10, 24)}
    for r in con.execute(
            "SELECT hora_entrada, min_ate_pesar FROM vw_jornada_cliente WHERE entrada >= ? AND entrada < ?",
            (ini, fim)):
        if r[0] in horas:
            horas[r[0]]["clientes"] += 1
            horas[r[0]]["pesar"].append(r[1])
    for r in con.execute(
            "SELECT hora, min_suja FROM vw_tempo_mesa_suja WHERE saiu_em >= ? AND saiu_em < ? AND conta_na_media = 1",
            (ini, fim)):
        if r[0] in horas:
            horas[r[0]]["suja"].append(r[1])
    for r in con.execute(
            "SELECT hora, SUM(receita), SUM(custo_estimado) FROM vw_pratos WHERE pesado_em >= ? AND pesado_em < ? GROUP BY hora",
            (ini, fim)):
        if r[0] in horas:
            horas[r[0]]["receita"], horas[r[0]]["custo"] = r[1], r[2]

    saida = []
    for h in horas.values():
        if not (h["clientes"] or h["suja"] or h["receita"]):
            continue
        saida.append({
            "hora": h["hora"], "clientes": h["clientes"],
            "min_ate_pesar": _media(h["pesar"]), "min_ate_pesar_p90": _percentil(h["pesar"], 90),
            "min_mesa_suja": _media(h["suja"]), "limpezas": len(h["suja"]),
            "margem": round((h["receita"] - h["custo"]) / h["receita"], 4) if h["receita"] else None,
        })
    return saida


def _saloes(con, ini, fim):
    saida = []
    for salao in ("Inferior", "Principal", "Superior"):
        v = [r[0] for r in con.execute(
            """SELECT min_suja FROM vw_tempo_mesa_suja WHERE salao = ? AND saiu_em >= ? AND saiu_em < ?
               AND conta_na_media = 1""", (salao, ini, fim))]
        saida.append({"salao": salao, "min_mesa_suja": _media(v), "p90": _percentil(v, 90), "limpezas": len(v)})
    return saida


def mesas_agora(con, agora=None):
    agora = agora or datetime.now()
    agora_txt = agora.strftime(FORMATO)
    abertas = {r["mesa_numero"]: r["saiu_em"] for r in con.execute(
        "SELECT mesa_numero, saiu_em FROM limpezas_mesa WHERE limpa_em IS NULL")}
    ocupadas = {r[0] for r in con.execute(
        """SELECT DISTINCT mesa_numero FROM comandas WHERE fechada_em IS NULL AND mesa_numero IS NOT NULL
           AND aberta_em >= ?""", ((agora - timedelta(hours=6)).strftime(FORMATO),))}
    mesas = []
    for r in con.execute("SELECT numero, salao FROM mesas ORDER BY numero"):
        if r["numero"] in abertas:
            minutos = (datetime.strptime(agora_txt, FORMATO) - datetime.strptime(abertas[r["numero"]], FORMATO))
            mesas.append({"numero": r["numero"], "salao": r["salao"], "status": "suja",
                          "minutos": max(0, round(minutos.total_seconds() / 60))})
        else:
            status = "ocupada" if r["numero"] in ocupadas else "livre"
            mesas.append({"numero": r["numero"], "salao": r["salao"], "status": status, "minutos": None})
    return mesas


ORIGENS_REAIS = "('planilha', 'api')"


def _r2(v):
    return round(v, 2) if v is not None else None


def _avaliacoes(con, ini, fim, so_reais=False):
    """Bloco da Dor 4. so_reais=True usa só respostas da planilha/API (ignora as simuladas)."""
    filtro = f" AND origem IN {ORIGENS_REAIS}" if so_reais else ""
    dist = {"comida": [0] * 5, "espera": [0] * 5, "limpeza": [0] * 5}
    for r in con.execute(
            f"""SELECT nota_comida, nota_espera, nota_limpeza FROM avaliacoes
                WHERE criada_em >= ? AND criada_em < ?{filtro}""", (ini, fim)):
        for chave, nota in zip(("comida", "espera", "limpeza"), r):
            if nota:
                dist[chave][nota - 1] += 1

    medias = con.execute(
        f"""SELECT COUNT(*), AVG(nota_comida), AVG(nota_espera), AVG(nota_limpeza) FROM avaliacoes
            WHERE criada_em >= ? AND criada_em < ?{filtro}""", (ini, fim)).fetchone()

    opiniao = {}
    for r in con.execute(
            f"""SELECT item, opiniao, COUNT(*) FROM vw_opiniao_itens WHERE criada_em >= ? AND criada_em < ?{filtro}
                GROUP BY item, opiniao""", (ini, fim)):
        opiniao.setdefault(r[0], {"item": r[0], "gostou": 0, "nao_gostou": 0})[r[1]] = r[2]
    opiniao = sorted(opiniao.values(), key=lambda x: x["gostou"] + x["nao_gostou"], reverse=True)

    temas = [{"tema": NOMES_TEMA.get(r[0], r[0]), "chave": r[0], "n": r[1]} for r in con.execute(
        f"""SELECT tema, COUNT(*) FROM avaliacoes WHERE criada_em >= ? AND criada_em < ? AND tema IS NOT NULL{filtro}
            GROUP BY tema ORDER BY 2 DESC""", (ini, fim))]

    motivos = [{"motivo": r[0], "n": r[1]} for r in con.execute(
        f"""SELECT motivo, COUNT(*) FROM avaliacoes WHERE criada_em >= ? AND criada_em < ? AND motivo IS NOT NULL{filtro}
            GROUP BY motivo ORDER BY 2 DESC""", (ini, fim))]

    # A nota de espera bate com o tempo medido pela comanda?
    filtro_a = filtro.replace("origem", "a.origem")
    espera_vs_nota = [{"nota": r[0], "min_medio": round(r[1], 1), "n": r[2]} for r in con.execute(
        f"""SELECT a.nota_espera, AVG(j.min_ate_pesar), COUNT(*)
            FROM avaliacoes a JOIN vw_jornada_cliente j ON j.comanda_id = a.comanda_id
            WHERE a.criada_em >= ? AND a.criada_em < ? AND a.nota_espera IS NOT NULL
              AND j.min_ate_pesar IS NOT NULL{filtro_a}
            GROUP BY a.nota_espera ORDER BY a.nota_espera""", (ini, fim))]

    comentarios = [dict(r) for r in con.execute(
        f"""SELECT criada_em, mesa_numero, nota_comida, nota_espera, nota_limpeza, comentario, tema, origem
            FROM avaliacoes WHERE criada_em >= ? AND criada_em < ? AND comentario IS NOT NULL{filtro}
            ORDER BY criada_em DESC LIMIT 8""", (ini, fim))]
    for c in comentarios:
        c["tema"] = NOMES_TEMA.get(c["tema"], c["tema"])

    por_origem = {(r[0] or "simulado"): r[1] for r in con.execute(
        "SELECT origem, COUNT(*) FROM avaliacoes WHERE criada_em >= ? AND criada_em < ? GROUP BY origem", (ini, fim))}
    return {"so_reais": so_reais, "respostas": medias[0],
            "media": {"comida": _r2(medias[1]), "espera": _r2(medias[2]), "limpeza": _r2(medias[3])},
            "por_origem": por_origem, "distribuicao": dist, "opiniao_itens": opiniao, "temas": temas,
            "motivos": motivos, "espera_vs_nota": espera_vs_nota, "comentarios": comentarios}


# ------------------------------------------------------------------ alertas

def _alertas(atual, anterior, mix, por_hora, saloes, mesas, av):
    """Regras simples que transformam os números em frases para o gerente."""
    alertas = []

    def add(nivel, titulo, texto):
        alertas.append({"nivel": nivel, "titulo": titulo, "texto": texto})

    # 1. Item que pesa no custo muito mais do que no prato
    if mix:
        caro = max(mix, key=lambda i: i["pct_custo"] - i["pct_peso"])
        if caro["pct_custo"] - caro["pct_peso"] > 0.05:
            add("atencao", f"{caro['item']} puxa o custo",
                f"É {_fmt_pct(caro['pct_peso'])} do peso servido, mas {_fmt_pct(caro['pct_custo'])} do custo da comida. "
                "Cada ponto a menos dele no prato médio aumenta a margem.")

    # 2. Pior horário de espera até a balança
    com_espera = [h for h in por_hora if h["min_ate_pesar"] is not None and h["clientes"] >= 10]
    if com_espera:
        pior = max(com_espera, key=lambda h: h["min_ate_pesar"])
        if pior["min_ate_pesar"] >= 8:
            add("critico" if pior["min_ate_pesar"] >= 11 else "atencao", f"Fila às {pior['hora']}h",
                f"Da entrada até a balança o cliente leva {_fmt_min(pior['min_ate_pesar'])} em média "
                f"(1 em cada 10 passa de {_fmt_min(pior['min_ate_pesar_p90'])}). "
                "Reforçar churrasqueira e reposição das cubas nesse horário.")

    # 3. Salão com mesa suja por mais tempo
    validos = [s for s in saloes if s["min_mesa_suja"] is not None]
    if len(validos) >= 2:
        pior, melhor = max(validos, key=lambda s: s["min_mesa_suja"]), min(validos, key=lambda s: s["min_mesa_suja"])
        if pior["min_mesa_suja"] - melhor["min_mesa_suja"] >= 1.5:
            add("atencao", f"Salão {pior['salao']} demora a limpar",
                f"Mesas ficam {_fmt_min(pior['min_mesa_suja'])} sujas, contra {_fmt_min(melhor['min_mesa_suja'])} "
                f"no {melhor['salao']}. Vale fixar um garçom de limpeza nesse salão no pico.")

    # 4. Mesas sujas agora
    paradas = [m for m in mesas if m["status"] == "suja" and m["minutos"] is not None and 10 <= m["minutos"] <= 90]
    if paradas:
        nums = ", ".join(str(m["numero"]) for m in sorted(paradas, key=lambda m: -m["minutos"])[:6])
        add("critico", f"{len(paradas)} mesa(s) suja(s) há mais de 10 min", f"Agora: mesas {nums}.")
    esquecidas = [m for m in mesas if m["status"] == "suja" and m["minutos"] is not None and m["minutos"] > 90]
    if esquecidas:
        nums = ", ".join(str(m["numero"]) for m in esquecidas[:8])
        add("atencao", f"{len(esquecidas)} mesa(s) marcada(s) suja(s) há mais de 90 min",
            f"Mesas {nums}: provavelmente já foram limpas e ninguém tocou 'limpa' na tela do garçom. "
            "Esses tempos ficam fora das médias.")

    # Nota da limpeza dada pelos clientes
    if av["media"]["limpeza"] is not None and av["respostas"] >= 5 and av["media"]["limpeza"] < 3.5:
        add("atencao", "Clientes reclamam da limpeza",
            f"Nota média de limpeza da mesa e do salão: {av['media']['limpeza']:.1f} de 5.".replace(".", ",", 1))

    # 5. Item mais criticado e pouco escolhido (candidato a sair do buffet)
    criticados = [o for o in av["opiniao_itens"] if o["nao_gostou"] >= 5]
    if criticados:
        pior = max(criticados, key=lambda o: o["nao_gostou"] / (o["gostou"] + o["nao_gostou"]))
        presenca = next((i["pct_pratos"] for i in mix if i["item"] == pior["item"]), None)
        extra = f" e aparece em só {_fmt_pct(presenca)} dos pratos" if presenca is not None else ""
        add("atencao", f"{pior['item']} não agrada",
            f"{pior['nao_gostou']} críticas contra {pior['gostou']} elogios{extra}. "
            "Revisar receita ou reduzir a cuba para evitar desperdício.")

    # 6. A nota de espera acompanha o tempo medido
    evn = {e["nota"]: e for e in av["espera_vs_nota"]}
    baixas = [evn[n] for n in (1, 2) if n in evn]
    altas = [evn[n] for n in (4, 5) if n in evn]
    if baixas and altas:
        b = sum(e["min_medio"] * e["n"] for e in baixas) / sum(e["n"] for e in baixas)
        a = sum(e["min_medio"] * e["n"] for e in altas) / sum(e["n"] for e in altas)
        if b - a >= 2:
            add("info", "A nota de espera confirma a medição",
                f"Quem deu nota 1-2 para espera levou {_fmt_min(b)} até a balança; quem deu 4-5 levou {_fmt_min(a)}. "
                "O tempo medido pela comanda é o que o cliente sente.")

    # 7. Margem caiu em relação ao período anterior
    if atual["margem"] is not None and anterior["margem"] is not None:
        dif = atual["margem"] - anterior["margem"]
        if dif <= -0.01:
            add("atencao", "Margem caiu",
                f"Margem estimada de {_fmt_pct(atual['margem'], 1)}, {abs(dif) * 100:.1f} p.p. abaixo do período anterior.".replace(".", ",", 1))
        elif dif >= 0.01:
            add("info", "Margem subiu",
                f"Margem estimada de {_fmt_pct(atual['margem'], 1)}, {dif * 100:.1f} p.p. acima do período anterior.".replace(".", ",", 1))

    ordem = {"critico": 0, "atencao": 1, "info": 2}
    return sorted(alertas, key=lambda a: ordem[a["nivel"]])


# ------------------------------------------------------------------ painel

def montar_painel(con, dias=7, agora=None, so_reais=False):
    agora = agora or datetime.now()
    dias = max(1, min(int(dias), 90))
    ant_ini, ini, fim = _janela(dias, agora)

    atual = _resumo(con, ini, fim)
    anterior = _resumo(con, ant_ini, ini)
    mix = _mix_itens(con, ini, fim)
    por_hora = _por_hora(con, ini, fim)
    saloes = _saloes(con, ini, fim)
    mesas = mesas_agora(con, agora)
    av = _avaliacoes(con, ini, fim, so_reais)
    simulado = con.execute("SELECT valor FROM meta WHERE chave = 'dados_simulados'").fetchone()

    return {
        "gerado_em": agora.strftime(FORMATO),
        "periodo": {"dias": dias, "inicio": ini, "fim": fim, "anterior_inicio": ant_ini},
        "dados_simulados": bool(simulado and simulado[0] == "1"),
        "resumo": atual,
        "resumo_anterior": anterior,
        "mix_itens": mix,
        "raio_x": _raio_x(con, ini, fim),
        "por_hora": por_hora,
        "saloes": saloes,
        "mesas_agora": mesas,
        "avaliacoes": av,
        "alertas": _alertas(atual, anterior, mix, por_hora, saloes, mesas, av),
        "planilha": planilha.estado(),
    }
