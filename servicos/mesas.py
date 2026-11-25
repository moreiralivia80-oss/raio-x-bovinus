"""
Controle de mesas - Bovinu'S
Guarda quando o cliente saiu e quando a mesa foi limpa, e calcula o tempo sujo.
Inclui: grade de mesas, desfazer, análise (tempo por horário / top mesas),
dados de demonstração e exportação em CSV.
"""
import csv
import io
import os
import random
import sqlite3
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify

mesas_bp = Blueprint("mesas", __name__)

# banco na pasta do projeto, não importa de onde o "python app.py" foi rodado
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bovinus.db")
TOTAL_MESAS = 90         # ~20 (inferior) + ~30 (principal) + ~40 (superior)

MINUTOS_SQL = "(julianday(limpa_em) - julianday(saiu_em)) * 1440"


def _conn():
    return sqlite3.connect(DB_PATH)


def _avisar_painel(funcao, mesa):
    """Repete o toque do garçom no banco do painel do gerente (seção Limpeza do salão).
    Se o painel falhar, a tela de mesas continua funcionando normalmente."""
    try:
        from painel import banco as painel_banco, eventos as painel_eventos
        con = painel_banco.conectar()
        try:
            painel_banco.criar_tabelas(con)
            getattr(painel_eventos, funcao)(con, mesa)
            con.commit()
        finally:
            con.close()
    except Exception as erro:
        print(f"[mesas] painel não atualizado ({funcao}, mesa {mesa}): {erro}")


def criar_tabela():
    with _conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mesas_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mesa INTEGER NOT NULL,
                saiu_em TEXT NOT NULL,
                limpa_em TEXT
            )
            """
        )


# ----------------------------- Aba do garçom -----------------------------
@mesas_bp.get("/api/mesas/estado")
def estado():
    """Lista as mesas que estão sujas agora."""
    with _conn() as conn:
        rows = conn.execute(
            "SELECT mesa FROM mesas_log WHERE limpa_em IS NULL"
        ).fetchall()
    return jsonify({"total": TOTAL_MESAS, "sujas": [r[0] for r in rows]})


@mesas_bp.post("/api/mesas/<int:mesa>/alternar")
def alternar(mesa):
    """Limpa -> suja (cliente saiu) ou suja -> limpa (garçom limpou)."""
    if not 1 <= mesa <= TOTAL_MESAS:
        return jsonify({"erro": "Mesa inválida"}), 400

    agora = datetime.now().isoformat()
    with _conn() as conn:
        suja = conn.execute(
            "SELECT id FROM mesas_log WHERE mesa = ? AND limpa_em IS NULL",
            (mesa,),
        ).fetchone()
        if suja:
            conn.execute(
                "UPDATE mesas_log SET limpa_em = ? WHERE id = ?", (agora, suja[0])
            )
            novo_estado = "limpa"
        else:
            conn.execute(
                "INSERT INTO mesas_log (mesa, saiu_em) VALUES (?, ?)", (mesa, agora)
            )
            novo_estado = "suja"
    _avisar_painel("mesa_saiu" if novo_estado == "suja" else "mesa_limpa", mesa)
    return jsonify({"mesa": mesa, "estado": novo_estado})


@mesas_bp.post("/api/mesas/desfazer")
def desfazer():
    """Desfaz o último toque (o evento mais recente, de saída ou de limpeza)."""
    with _conn() as conn:
        ultimo = conn.execute(
            "SELECT id, mesa, saiu_em, limpa_em FROM mesas_log "
            "ORDER BY COALESCE(limpa_em, saiu_em) DESC LIMIT 1"
        ).fetchone()
        if not ultimo:
            return jsonify({"erro": "Nada para desfazer"}), 400
        id_, mesa, _saiu, limpa = ultimo
        if limpa:   # último toque foi "limpa" -> volta a ficar suja
            conn.execute("UPDATE mesas_log SET limpa_em = NULL WHERE id = ?", (id_,))
        else:       # último toque foi "cliente saiu" -> apaga o registro
            conn.execute("DELETE FROM mesas_log WHERE id = ?", (id_,))
    _avisar_painel("mesa_desfazer", mesa)
    return jsonify({"mesa": mesa, "desfeito": True})


# ------------------------------ Aba de análise ---------------------------
@mesas_bp.get("/api/mesas/resumo")
def resumo():
    """Dados para a análise e para o painel do gerente (tempo sujo, em minutos)."""
    with _conn() as conn:
        media, maior, ciclos = conn.execute(
            f"SELECT AVG({MINUTOS_SQL}), MAX({MINUTOS_SQL}), COUNT(*) "
            "FROM mesas_log WHERE limpa_em IS NOT NULL"
        ).fetchone()
        por_hora = conn.execute(
            f"SELECT strftime('%H', saiu_em) AS hora, AVG({MINUTOS_SQL}) "
            "FROM mesas_log WHERE limpa_em IS NOT NULL GROUP BY hora ORDER BY hora"
        ).fetchall()
        por_mesa = conn.execute(
            f"SELECT mesa, AVG({MINUTOS_SQL}) AS minutos "
            "FROM mesas_log WHERE limpa_em IS NOT NULL "
            "GROUP BY mesa ORDER BY minutos DESC LIMIT 10"
        ).fetchall()
    return jsonify(
        {
            "media_minutos": round(media, 1) if media else None,
            "maior_minutos": round(maior, 1) if maior else None,
            "ciclos": ciclos,
            "por_hora": [{"hora": f"{h}h", "minutos": round(m, 1)} for h, m in por_hora],
            "top_mesas": [{"mesa": n, "minutos": round(m, 1)} for n, m in por_mesa],
        }
    )


@mesas_bp.post("/api/mesas/demo")
def gerar_demo():
    """Cria 80 registros falsos só para o painel não ficar vazio na apresentação."""
    base = datetime.now().replace(hour=11, minute=0, second=0, microsecond=0)
    with _conn() as conn:
        for _ in range(80):
            mesa = random.randint(1, TOTAL_MESAS)
            saiu = base + timedelta(minutes=random.randint(0, 240))
            pico = 12 <= saiu.hour < 14   # no pico a limpeza demora mais
            espera = random.randint(6, 18) if pico else random.randint(2, 9)
            limpa = saiu + timedelta(minutes=espera, seconds=random.randint(0, 59))
            conn.execute(
                "INSERT INTO mesas_log (mesa, saiu_em, limpa_em) VALUES (?, ?, ?)",
                (mesa, saiu.isoformat(), limpa.isoformat()),
            )
    return jsonify({"criados": 80})


@mesas_bp.get("/api/mesas/exportar.csv")
def exportar_csv():
    """Baixa os ciclos completos em CSV (para cruzar com o Forms no pandas)."""
    with _conn() as conn:
        rows = conn.execute(
            f"SELECT id, mesa, saiu_em, limpa_em, ROUND({MINUTOS_SQL}, 2) "
            "FROM mesas_log WHERE limpa_em IS NOT NULL ORDER BY saiu_em"
        ).fetchall()
    saida = io.StringIO()
    writer = csv.writer(saida)
    writer.writerow(["id", "mesa", "saiu_em", "limpa_em", "minutos_sujo"])
    writer.writerows(rows)
    return Response(
        saida.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=mesas_log.csv"},
    )
