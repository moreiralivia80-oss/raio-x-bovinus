"""Gravação dos dados do salão: pips da comanda, pratos, mesas e avaliações.

Todas as funções recebem uma conexão aberta e NÃO fazem commit:
quem chama decide (a rota da API faz commit; o simulador grava tudo de uma vez).
"""
import re
import unicodedata
from datetime import datetime, timedelta

from .banco import FORMATO, texto_data

TIPOS_PIP = ("entrada", "balanca", "atendimento_mesa", "pagamento")
JANELA_COMANDA_H = 12  # comanda aberta há mais que isso é considerada esquecida
LEITURA_REPETIDA_S = 60  # mesma comanda no mesmo ponto dentro desse tempo = leitura repetida
DESFAZER_S = 120  # o garçom pode desfazer um toque errado até 2 min depois

# Palavras-chave para separar o assunto do comentário sem gastar API.
# Se o Gemini já classificou, o tema dele é usado.
TEMAS = {
    "espera": ("fila", "demor", "espera", "esperei", "lento", "tempo", "churrasqueira cheia"),
    "limpeza": ("suja", "sujo", "limp", "migalha", "bandeja", "guardanapo"),
    "atendimento": ("garcom", "garçom", "atend", "educad", "simpatic", "grosso", "bebida"),
    "comida": ("carne", "picanha", "fria", "frio", "salgad", "sabor", "gostos", "delicios",
               "comida", "tempero", "ponto", "seco", "seca", "buffet", "sobremesa", "salada", "prato",
               "agradavel", "gostoso", "massa", "arroz", "feij"),
}


def _sem_acento(texto):
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()


def classificar_tema(comentario):
    texto = _sem_acento(comentario)
    if not texto.strip():
        return None
    pontos = {tema: sum(_sem_acento(p) in texto for p in palavras) for tema, palavras in TEMAS.items()}
    tema, nota = max(pontos.items(), key=lambda x: x[1])
    return tema if nota else "outro"


def _minutos(inicio, fim):
    a = datetime.strptime(inicio, FORMATO)
    b = datetime.strptime(fim, FORMATO)
    return round((b - a).total_seconds() / 60, 1)


# ---------------------------------------------------------------- comanda

def _comanda_aberta(con, codigo, momento):
    limite = (datetime.strptime(momento, FORMATO) - timedelta(hours=JANELA_COMANDA_H)).strftime(FORMATO)
    return con.execute(
        """SELECT * FROM comandas WHERE codigo = ? AND fechada_em IS NULL AND aberta_em >= ?
           ORDER BY id DESC LIMIT 1""",
        (codigo, limite),
    ).fetchone()


def _leitura_repetida(con, codigo, tipo, momento, id_cliente):
    """Mesma leitura já gravada? (reenvio da fila offline ou leitor que lê 2 vezes)"""
    if id_cliente:
        r = con.execute(
            """SELECT e.comanda_id, e.momento FROM eventos_comanda e WHERE e.id_cliente = ?""", (id_cliente,)
        ).fetchone()
        if r:
            return r
    m = datetime.strptime(momento, FORMATO)
    return con.execute(
        """SELECT e.comanda_id, e.momento FROM eventos_comanda e JOIN comandas c ON c.id = e.comanda_id
           WHERE c.codigo = ? AND e.tipo = ? AND e.momento BETWEEN ? AND ?
           ORDER BY e.id DESC LIMIT 1""",
        (codigo, tipo, (m - timedelta(seconds=LEITURA_REPETIDA_S)).strftime(FORMATO),
         (m + timedelta(seconds=LEITURA_REPETIDA_S)).strftime(FORMATO)),
    ).fetchone()


def _mesa_existe(con, mesa):
    if not con.execute("SELECT 1 FROM mesas WHERE numero = ?", (mesa,)).fetchone():
        raise ValueError(f"Mesa {mesa} não existe no cadastro.")


def pipar(con, codigo, tipo, momento=None, mesa=None, ponto=None, id_cliente=None):
    """Registra a leitura (pip) da comanda num ponto do salão.

    entrada          -> abre um novo uso da comanda
    balanca          -> cliente pesou o prato (tempo de se servir = balanca - entrada)
    atendimento_mesa -> garçom atendeu a mesa (liga comanda <-> mesa); se a mesa ainda
                        estava marcada como suja, ela é liberada (fora da média de limpeza)
    pagamento        -> fecha a comanda; se era a última comanda aberta da mesa,
                        a mesa entra automaticamente como "suja"
    A mesma comanda lida no mesmo ponto em menos de 60 s é ignorada (leitura repetida).
    """
    codigo = str(codigo or "").strip()
    if not codigo:
        raise ValueError("Informe o código da comanda.")
    if tipo not in TIPOS_PIP:
        raise ValueError(f"Tipo de leitura inválido: {tipo}")
    momento = texto_data(momento)
    try:
        mesa = int(mesa) if mesa not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("Número da mesa inválido.") from None
    if mesa is not None:
        _mesa_existe(con, mesa)
    if tipo == "atendimento_mesa" and mesa is None:
        raise ValueError("Informe a mesa atendida.")
    id_cliente = str(id_cliente).strip()[:64] if id_cliente else None

    repetida = _leitura_repetida(con, codigo, tipo, momento, id_cliente)
    if repetida:
        return {"comanda_id": repetida[0], "codigo": codigo, "tipo": tipo, "momento": repetida[1],
                "repetida": True, "aviso": "Leitura repetida: já estava registrada, não foi contada de novo."}

    comanda = None if tipo == "entrada" else _comanda_aberta(con, codigo, momento)
    if comanda is None:
        cur = con.execute("INSERT INTO comandas (codigo, aberta_em) VALUES (?, ?)", (codigo, momento))
        comanda_id, aberta_em = cur.lastrowid, momento
    else:
        comanda_id, aberta_em = comanda["id"], comanda["aberta_em"]

    con.execute(
        """INSERT INTO eventos_comanda (comanda_id, tipo, momento, mesa_numero, ponto, id_cliente)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (comanda_id, tipo, momento, mesa, ponto, id_cliente),
    )
    if mesa is not None:
        con.execute("UPDATE comandas SET mesa_numero = ? WHERE id = ?", (mesa, comanda_id))
        # cliente novo sentado numa mesa que ninguém marcou como limpa: libera a mesa
        aberta = con.execute(
            "SELECT id FROM limpezas_mesa WHERE mesa_numero = ? AND limpa_em IS NULL AND saiu_em <= ?",
            (mesa, momento)).fetchone()
        if aberta:
            con.execute("UPDATE limpezas_mesa SET limpa_em = ?, limpa_origem = 'novo_cliente' WHERE id = ?",
                        (momento, aberta["id"]))

    resposta = {"comanda_id": comanda_id, "codigo": codigo, "tipo": tipo, "momento": momento}
    entrada = con.execute(
        "SELECT MIN(momento) FROM eventos_comanda WHERE comanda_id = ? AND tipo = 'entrada'", (comanda_id,)
    ).fetchone()[0]
    if entrada and tipo != "entrada":
        resposta["minutos_desde_entrada"] = _minutos(entrada, momento)
    if comanda is None and tipo != "entrada":
        resposta["aviso"] = "Comanda sem pip de entrada: o tempo de espera desta comanda não será medido."

    if tipo == "pagamento":
        con.execute("UPDATE comandas SET fechada_em = ? WHERE id = ?", (momento, comanda_id))
        mesa_da_comanda = con.execute("SELECT mesa_numero FROM comandas WHERE id = ?", (comanda_id,)).fetchone()[0]
        if mesa_da_comanda is not None:
            outras_abertas = con.execute(
                """SELECT COUNT(*) FROM comandas WHERE mesa_numero = ? AND fechada_em IS NULL
                   AND aberta_em >= ?""",
                (mesa_da_comanda, (datetime.strptime(momento, FORMATO) - timedelta(hours=JANELA_COMANDA_H)).strftime(FORMATO)),
            ).fetchone()[0]
            if outras_abertas == 0:
                resposta["mesa_suja"] = mesa_saiu(con, mesa_da_comanda, momento, origem="caixa")
    return resposta


# ---------------------------------------------------------------- Raio-X

def registrar_prato(con, resultado, codigo_comanda=None, momento=None):
    """Salva o resultado do Raio-X (o dicionário de servicos/custos.calcular).

    Se vier o código da comanda, também registra o pip de 'balanca'.
    """
    momento = texto_data(momento)
    comanda_id = None
    if codigo_comanda:
        comanda_id = pipar(con, codigo_comanda, "balanca", momento, ponto="Balança")["comanda_id"]
    cur = con.execute(
        """INSERT INTO pratos (comanda_id, pesado_em, peso_g, receita, custo_estimado, precisao, origem)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (comanda_id, momento, float(resultado["peso_g"]), float(resultado["receita"]),
         float(resultado["custo_estimado"]), resultado.get("precisao"), resultado.get("origem", "ia")),
    )
    prato_id = cur.lastrowid
    con.executemany(
        """INSERT INTO itens_prato (prato_id, item, categoria, percentual, peso_g, custo, confianca)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(prato_id, i["nome"], i.get("categoria") or "outro", float(i["percentual"]), float(i["peso_g"]),
          float(i["custo"]), i.get("confianca")) for i in resultado.get("itens", [])],
    )
    return prato_id


# ---------------------------------------------------------------- mesas

def mesa_saiu(con, mesa, momento=None, origem="garcom"):
    """Cliente saiu: a mesa fica vermelha. Tocar de novo não duplica."""
    _mesa_existe(con, mesa)
    momento = texto_data(momento)
    aberta = con.execute(
        "SELECT id, saiu_em FROM limpezas_mesa WHERE mesa_numero = ? AND limpa_em IS NULL", (mesa,)
    ).fetchone()
    if aberta:
        return {"limpeza_id": aberta["id"], "mesa": mesa, "saiu_em": aberta["saiu_em"], "ja_estava_suja": True}
    cur = con.execute(
        "INSERT INTO limpezas_mesa (mesa_numero, saiu_em, origem) VALUES (?, ?, ?)", (mesa, momento, origem)
    )
    return {"limpeza_id": cur.lastrowid, "mesa": mesa, "saiu_em": momento, "ja_estava_suja": False}


def mesa_limpa(con, mesa, momento=None):
    """Mesa limpa: fica verde. Devolve quantos minutos ela ficou suja."""
    _mesa_existe(con, mesa)
    momento = texto_data(momento)
    aberta = con.execute(
        "SELECT id, saiu_em FROM limpezas_mesa WHERE mesa_numero = ? AND limpa_em IS NULL", (mesa,)
    ).fetchone()
    if not aberta:
        return {"mesa": mesa, "estava_suja": False}
    limpa_em = max(momento, aberta["saiu_em"])  # toque guardado offline nunca fica antes do "saiu"
    con.execute("UPDATE limpezas_mesa SET limpa_em = ?, limpa_origem = 'garcom' WHERE id = ?", (limpa_em, aberta["id"]))
    return {"mesa": mesa, "estava_suja": True, "minutos_suja": _minutos(aberta["saiu_em"], limpa_em)}


def mesa_desfazer(con, mesa, momento=None):
    """Desfaz o último toque do garçom nessa mesa (até DESFAZER_S segundos depois)."""
    _mesa_existe(con, mesa)
    agora = datetime.strptime(texto_data(momento), FORMATO)
    limite = (agora - timedelta(seconds=DESFAZER_S)).strftime(FORMATO)
    ultima = con.execute(
        "SELECT * FROM limpezas_mesa WHERE mesa_numero = ? ORDER BY id DESC LIMIT 1", (mesa,)).fetchone()
    if ultima and ultima["limpa_em"] and ultima["limpa_origem"] == "garcom" and ultima["limpa_em"] >= limite:
        con.execute("UPDATE limpezas_mesa SET limpa_em = NULL, limpa_origem = NULL WHERE id = ?", (ultima["id"],))
        return {"mesa": mesa, "desfeito": "limpa", "status": "suja"}
    if ultima and not ultima["limpa_em"] and ultima["origem"] == "garcom" and ultima["saiu_em"] >= limite:
        con.execute("DELETE FROM limpezas_mesa WHERE id = ?", (ultima["id"],))
        return {"mesa": mesa, "desfeito": "saiu", "status": "livre"}
    raise ValueError("Nada para desfazer nessa mesa (o prazo é de 2 minutos).")


# ---------------------------------------------------------------- avaliação

SEM_ITEM = {"estava tudo bom", "tudo bom", "nada", "nenhum", "nenhum item", "nao", "-"}


def _nota(valor):
    """Aceita 5, "5" ou "5 - Excelente" (formato do Google Forms)."""
    if valor in (None, ""):
        return None
    achado = re.match(r"\s*(\d+)", str(valor))
    if not achado:
        raise ValueError(f"Nota inválida: {valor!r}. As notas vão de 1 a 5.")
    nota = int(achado.group(1))
    if not 1 <= nota <= 5:
        raise ValueError("As notas vão de 1 a 5.")
    return nota


def _itens(con, valor):
    """'Churrasco: Picanha, Saladas: Vinagrete' -> ['Picanha', 'Vinagrete'] (nomes do cadastro do buffet)."""
    if isinstance(valor, str):
        valor = valor.replace(";", ",").split(",")
    cadastro = {_sem_acento(r[0]): r[0] for r in con.execute("SELECT nome FROM itens_buffet")}
    itens = []
    for bruto in valor or []:
        nome = str(bruto).strip()
        if ":" in nome:  # tira a categoria do formulário ("Churrasco: ")
            nome = nome.split(":", 1)[1].strip()
        if not nome or _sem_acento(nome) in SEM_ITEM:
            continue
        nome = cadastro.get(_sem_acento(nome), nome[:60])
        if nome not in itens:
            itens.append(nome)
    return itens


def registrar_avaliacao(con, dados, momento=None):
    """dados: mesa, codigo_comanda, nota_comida, nota_espera, nota_limpeza, gostou=[...], nao_gostou=[...],
    motivo, comentario, tema (opcional), beneficio (desconto/cashback), origem, chave_origem.

    Se chave_origem já existe (mesma linha da planilha), não grava de novo e devolve o id existente."""
    if dados.get("chave_origem"):
        existe = con.execute("SELECT id FROM avaliacoes WHERE chave_origem = ?", (dados["chave_origem"],)).fetchone()
        if existe:
            return existe["id"]
    momento = texto_data(dados.get("criada_em") or momento)
    comanda_id = None
    if dados.get("codigo_comanda"):
        linha = con.execute(
            "SELECT id FROM comandas WHERE codigo = ? AND aberta_em <= ? ORDER BY id DESC LIMIT 1",
            (str(dados["codigo_comanda"]).strip(), momento),
        ).fetchone()
        comanda_id = linha["id"] if linha else None
    mesa = None
    if dados.get("mesa") not in (None, ""):
        achado = re.search(r"\d+", str(dados["mesa"]))
        mesa = int(achado.group()) if achado else None
        if mesa is not None and not con.execute("SELECT 1 FROM mesas WHERE numero = ?", (mesa,)).fetchone():
            mesa = None  # mesa digitada errada: guarda a resposta mesmo assim
    comentario = (dados.get("comentario") or "").strip()[:500] or None
    nao_gostou = _itens(con, dados.get("nao_gostou"))
    motivo = (dados.get("motivo") or "").strip()[:200] or None
    cur = con.execute(
        """INSERT INTO avaliacoes (criada_em, mesa_numero, comanda_id, nota_comida, nota_espera, nota_limpeza,
                                   comentario, tema, beneficio, motivo, origem, chave_origem)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (momento, mesa, comanda_id, _nota(dados.get("nota_comida")), _nota(dados.get("nota_espera")),
         _nota(dados.get("nota_limpeza")), comentario, dados.get("tema") or classificar_tema(comentario),
         dados.get("beneficio"), motivo if nao_gostou else None,  # motivo só vale se algum item foi criticado
         dados.get("origem") or "api", dados.get("chave_origem")),
    )
    avaliacao_id = cur.lastrowid
    con.executemany(
        "INSERT INTO avaliacao_itens (avaliacao_id, item, opiniao) VALUES (?, ?, ?)",
        [(avaliacao_id, item, "gostou") for item in _itens(con, dados.get("gostou"))]
        + [(avaliacao_id, item, "nao_gostou") for item in nao_gostou],
    )
    return avaliacao_id
