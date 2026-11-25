"""Rotas do painel (Flask Blueprint): telas, API de leitura e API de gravação.

Telas
    /painel             painel do gerente (pede login)
    /painel/login       login do gerente
    /garcom             mesas do salão para o garçom (cliente saiu / limpa / desfazer)
    /pipar              estação de leitura da comanda (entrada, balança, garçom na mesa, caixa)

API de gravação (o que alimenta o painel)
    POST /api/comanda/pipar          {"codigo": "123", "tipo": "entrada|balanca|atendimento_mesa|pagamento", "mesa": 12}
    POST /api/mesas/<n>/saiu         garçom tocou "cliente saiu"
    POST /api/mesas/<n>/limpa        garçom tocou "limpa"
    POST /api/mesas/<n>/desfazer     desfaz o último toque (até 2 min)
    POST /api/pratos                 resultado do Raio-X (+ "codigo_comanda")
    POST /api/avaliacoes             uma resposta de avaliação (outra origem que não a planilha)
    POST /api/painel/sincronizar     baixa agora as respostas da planilha do Google Forms (gerente)

API de leitura
    GET  /api/mesas                          situação de todas as mesas agora
    GET  /api/painel/dados?dias=7&reais=1    tudo que o painel mostra, em JSON
    GET  /api/painel/exportar/<tabela>.csv   tabelas e views para Excel / Power BI
    GET  /painel/foto/<id>                   foto de um prato registrado pelo Raio-X
"""
import csv
import hmac
import io
import os
import sqlite3
from datetime import datetime
from functools import wraps

from flask import (Blueprint, Response, abort, g, jsonify, redirect, render_template, request,
                   send_from_directory, session, url_for)

from . import banco, eventos, metricas, planilha

bp = Blueprint("painel", __name__, template_folder="templates", static_folder="static",
               static_url_path="/painel-static")

EXPORTAVEIS = ("vw_jornada_cliente", "vw_tempo_mesa_suja", "vw_pratos", "vw_mix_itens", "vw_opiniao_itens",
               "comandas", "eventos_comanda", "pratos", "itens_prato", "limpezas_mesa", "avaliacoes",
               "avaliacao_itens", "mesas", "itens_buffet")


@bp.record_once
def _preparar(_estado):
    con = banco.conectar()
    banco.criar_tabelas(con)
    con.close()
    planilha.iniciar_sincronizacao_automatica()


def db():
    if "painel_db" not in g:
        g.painel_db = banco.conectar()
    return g.painel_db


@bp.teardown_app_request
def _fechar(_erro):
    con = g.pop("painel_db", None)
    if con is not None:
        con.close()


# ------------------------------------------------------------------ login

def _credenciais():
    return os.environ.get("PAINEL_USUARIO", "gerente"), os.environ.get("PAINEL_SENHA", "bovinus2026")


def login_obrigatorio(func):
    @wraps(func)
    def protegido(*args, **kwargs):
        if session.get("painel_gerente"):
            return func(*args, **kwargs)
        # Modo apresentação: sem login, mas só para quem acessa do próprio computador (telão do hackathon)
        if os.environ.get("PAINEL_DEMO_SEM_LOGIN") == "1" and request.remote_addr in ("127.0.0.1", "::1"):
            return func(*args, **kwargs)
        if request.path.startswith("/api/"):
            return jsonify(erro="Faça login na área do gerente."), 401
        return redirect(url_for("painel.login", proximo=request.path))
    return protegido


@bp.route("/painel/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        usuario, senha = _credenciais()
        ok_usuario = hmac.compare_digest(request.form.get("usuario", ""), usuario)
        ok_senha = hmac.compare_digest(request.form.get("senha", ""), senha)
        if ok_usuario and ok_senha:
            session["painel_gerente"] = True
            proximo = request.args.get("proximo", "")
            return redirect(proximo if proximo.startswith("/") and not proximo.startswith("//") else url_for("painel.painel"))
        erro = "Usuário ou senha incorretos."
    return render_template("painel/login.html", erro=erro), (401 if erro else 200)


@bp.route("/painel/sair")
def sair():
    session.pop("painel_gerente", None)
    return redirect(url_for("painel.login"))


# ------------------------------------------------------------------ telas

@bp.route("/painel")
@login_obrigatorio
def painel():
    return render_template("painel/painel.html")


@bp.route("/pipar")
def pipar_tela():
    return render_template("painel/pipar.html", tipos=eventos.TIPOS_PIP)


@bp.route("/garcom")
def garcom_tela():
    return render_template("painel/garcom.html")


# ------------------------------------------------------------------ leitura

@bp.get("/api/painel/dados")
@login_obrigatorio
def dados():
    return jsonify(metricas.montar_painel(db(), request.args.get("dias", 7, type=int),
                                          so_reais=request.args.get("reais") == "1"))


@bp.post("/api/painel/sincronizar")
@login_obrigatorio
def sincronizar():
    return jsonify(planilha.sincronizar())


def _celula_csv(valor):
    if valor is None:
        return ""
    if isinstance(valor, float):
        return str(valor).replace(".", ",")
    texto = str(valor)
    # comentário de cliente que começa com = + - @ viraria fórmula no Excel: vira texto
    if texto[:1] in ("=", "+", "-", "@") and not texto.lstrip("+-").replace(",", "").replace(".", "").isdigit():
        return "'" + texto
    return valor


@bp.get("/api/painel/exportar/<nome>.csv")
@login_obrigatorio
def exportar(nome):
    if nome not in EXPORTAVEIS:
        return jsonify(erro="Tabela não disponível para exportação.", disponiveis=EXPORTAVEIS), 404
    cursor = db().execute(f"SELECT * FROM {nome}")  # nome validado pela lista acima
    saida = io.StringIO()
    saida.write("﻿")  # BOM: o Excel abre acentos corretamente
    escritor = csv.writer(saida, delimiter=";")
    escritor.writerow([c[0] for c in cursor.description])
    for linha in cursor:
        escritor.writerow([_celula_csv(v) for v in linha])
    return Response(saida.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={nome}.csv"})


@bp.get("/painel/foto/<int:prato_id>")
@login_obrigatorio
def foto_prato(prato_id):
    """Foto de um prato registrado pelo Raio-X (só para o gerente)."""
    linha = db().execute("SELECT foto FROM pratos WHERE id = ?", (prato_id,)).fetchone()
    if not linha or not linha["foto"]:
        abort(404)
    return send_from_directory(banco.pasta_fotos(), linha["foto"], max_age=3600)


@bp.get("/api/mesas")
def mesas_agora():
    return jsonify(metricas.mesas_agora(db(), datetime.now()))


# ------------------------------------------------------------------ gravação

def _gravar(funcao, *args, **kwargs):
    con = db()
    try:
        resultado = funcao(con, *args, **kwargs)
        con.commit()
        return resultado, None
    except (ValueError, KeyError, TypeError, sqlite3.IntegrityError) as erro:
        con.rollback()
        return None, str(erro)


def _corpo():
    return request.get_json(silent=True) or request.form.to_dict()


@bp.post("/api/comanda/pipar")
def api_pipar():
    d = _corpo()
    r, erro = _gravar(eventos.pipar, d.get("codigo"), d.get("tipo"), d.get("momento"), d.get("mesa"),
                      d.get("ponto"), d.get("id_cliente"))
    return (jsonify(erro=erro), 400) if erro else (jsonify(r), 200 if r.get("repetida") else 201)


@bp.post("/api/mesas/<int:numero>/saiu")
def api_mesa_saiu(numero):
    r, erro = _gravar(eventos.mesa_saiu, numero, _corpo().get("momento"))
    return (jsonify(erro=erro), 400) if erro else jsonify(r)


@bp.post("/api/mesas/<int:numero>/limpa")
def api_mesa_limpa(numero):
    r, erro = _gravar(eventos.mesa_limpa, numero, _corpo().get("momento"))
    return (jsonify(erro=erro), 400) if erro else jsonify(r)


@bp.post("/api/mesas/<int:numero>/desfazer")
def api_mesa_desfazer(numero):
    r, erro = _gravar(eventos.mesa_desfazer, numero)
    return (jsonify(erro=erro), 400) if erro else jsonify(r)


@bp.post("/api/pratos")
def api_prato():
    d = _corpo()
    r, erro = _gravar(eventos.registrar_prato, d, d.get("codigo_comanda"), d.get("momento"))
    return (jsonify(erro=erro), 400) if erro else (jsonify(prato_id=r), 201)


@bp.post("/api/avaliacoes")
def api_avaliacao():
    r, erro = _gravar(eventos.registrar_avaliacao, _corpo())
    return (jsonify(erro=erro), 400) if erro else (jsonify(avaliacao_id=r), 201)
