"""Raio-X Bovinu'S | servidor Flask.

Rodar:
    pip install -r requirements.txt
    python app.py
Abrir: http://localhost:5000
"""
import os

from flask import Flask, jsonify, render_template, request, url_for


def carregar_env(caminho=".env"):
    """Lê o arquivo .env (CHAVE=valor) e coloca nas variáveis de ambiente.
    O .env fica só no seu computador: ele está no .gitignore e não vai para o GitHub."""
    pasta = os.path.dirname(os.path.abspath(__file__))
    caminho = os.path.join(pasta, caminho)
    if not os.path.exists(caminho):
        # primeira vez: cria o .env vazio a partir do modelo, só para colar a chave
        modelo = os.path.join(pasta, ".env.example")
        if os.path.exists(modelo):
            with open(modelo, encoding="utf-8") as origem, open(caminho, "w", encoding="utf-8") as destino:
                destino.write(origem.read())
            print("Arquivo .env criado na pasta do projeto. Cole a chave do Gemini nele e rode de novo.")
        return
    with open(caminho, encoding="utf-8-sig") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            valor = valor.strip().strip('"').strip("'")
            if valor:
                os.environ.setdefault(chave.strip(), valor)


carregar_env()

from servicos import custos, gemini  # noqa: E402  (depois do .env, para já ler a chave)
from servicos.mesas import criar_tabela, mesas_bp  # noqa: E402

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # fotos de até 10 MB

criar_tabela()                      # cria a tabela de mesas no banco, se ainda não existir
app.register_blueprint(mesas_bp)    # ativa as rotas /api/mesas/...


@app.context_processor
def arquivos_estaticos():
    """estatico('js/raio-x.js') gera o link com a data do arquivo.
    Assim o navegador sempre baixa a versão nova depois de um Pull, sem precisar limpar o cache."""
    def estatico(nome):
        caminho = os.path.join(app.static_folder, nome)
        versao = int(os.path.getmtime(caminho)) if os.path.exists(caminho) else 0
        return url_for("static", filename=nome, v=versao)
    return {"estatico": estatico, "ia_ligada": gemini.tem_chave(), "demo_ligado": gemini.demo_ligado()}


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
    if analise is None:  # sem IA: não inventa alimentos
        return jsonify(erro=aviso), 503
    resultado = custos.calcular(peso_g, analise)
    resultado["origem"] = origem
    resultado["aviso"] = aviso
    return jsonify(resultado)


@app.errorhandler(413)
def foto_grande(_):
    return jsonify(erro="A foto é grande demais. Use uma foto de até 10 MB."), 413


if __name__ == "__main__":
    if gemini.tem_chave():
        modo = "IA ligada (Gemini)"
    elif gemini.demo_ligado():
        modo = "DEMONSTRAÇÃO (resultados de exemplo, a foto não é analisada)"
    else:
        modo = "IA DESLIGADA: defina GEMINI_API_KEY para analisar as fotos"
    print(f"Raio-X Bovinu'S: {modo}")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
