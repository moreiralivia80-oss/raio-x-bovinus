"""Raio-X Bovinu'S | servidor Flask.

Rodar:
    pip install -r requirements.txt
    python app.py
Abrir: http://localhost:5000
"""
import os

from flask import Flask, jsonify, render_template, request, url_for

from servicos import custos, gemini

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # fotos de até 10 MB


@app.context_processor
def arquivos_estaticos():
    """estatico('js/raio-x.js') gera o link com a data do arquivo.
    Assim o navegador sempre baixa a versão nova depois de um Pull, sem precisar limpar o cache."""
    def estatico(nome):
        caminho = os.path.join(app.static_folder, nome)
        versao = int(os.path.getmtime(caminho)) if os.path.exists(caminho) else 0
        return url_for("static", filename=nome, v=versao)
    return {"estatico": estatico, "ia_ligada": gemini.tem_chave()}


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/raio-x")
def raio_x():
    return render_template("raio_x.html")


@app.route("/mesas")
def mesas():
    return render_template("mesas.html")


@app.route("/gerente/login")
def gerente_login():
    return render_template("gerente_login.html")


@app.route("/gerente")
def gerente():
    return render_template("gerente.html")


@app.route("/avaliacao")
def avaliacao():
    return render_template("avaliacao.html")


@app.post("/api/raio-x/analisar")
def api_analisar():
    """Recebe a foto e o peso do prato e devolve itens, precisão, custo e margem."""
    foto = request.files.get("foto")
    if not foto:
        return jsonify(erro="Tire ou envie a foto do prato."), 400
    try:
        peso_g = float(request.form.get("peso_g", "").replace(",", "."))
    except ValueError:
        return jsonify(erro="Informe o peso do prato em gramas."), 400
    if not 1 <= peso_g <= 3000:
        return jsonify(erro="O peso precisa estar entre 1 g e 3000 g."), 400

    foto_bytes = foto.read()
    analise, origem, aviso = gemini.analisar(foto_bytes, foto.mimetype, custos.nomes_itens())
    resultado = custos.calcular(peso_g, analise)
    resultado["origem"] = origem
    resultado["aviso"] = aviso
    return jsonify(resultado)


@app.errorhandler(413)
def foto_grande(_):
    return jsonify(erro="A foto é grande demais. Use uma foto de até 10 MB."), 413


if __name__ == "__main__":
    modo = "IA (Gemini)" if gemini.tem_chave() else "demonstração (sem GEMINI_API_KEY)"
    print(f"Raio-X Bovinu'S rodando em modo {modo}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
