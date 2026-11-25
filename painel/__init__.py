"""Painel Gerencial Bovinu'S.

Uso no app do Raio-X (app.py do grupo):

    from painel import bp as painel_bp, registrar_prato_do_raio_x
    app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")
    app.register_blueprint(painel_bp)

E, dentro de api_analisar(), depois de calcular o resultado:

    registrar_prato_do_raio_x(resultado, request.form.get("comanda"), foto_bytes)
"""
from . import banco, eventos, metricas  # noqa: F401
from .rotas import bp  # noqa: F401


def registrar_prato_do_raio_x(resultado, codigo_comanda=None, foto_bytes=None):
    """Atalho para o Raio-X salvar cada prato analisado (abre e fecha a conexão sozinho).
    Se vier a foto, ela é guardada em dados/fotos/prato_<id>.jpg."""
    con = banco.conectar()
    try:
        banco.criar_tabelas(con)
        prato_id = eventos.registrar_prato(con, resultado, codigo_comanda or None)
        if foto_bytes:
            nome = f"prato_{prato_id}.jpg"
            (banco.pasta_fotos() / nome).write_bytes(foto_bytes)
            con.execute("UPDATE pratos SET foto = ? WHERE id = ?", (nome, prato_id))
        con.commit()
        return prato_id
    finally:
        con.close()
