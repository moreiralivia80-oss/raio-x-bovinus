"""Análise da foto do prato com a API do Google Gemini.

Configure a chave na variável de ambiente GEMINI_API_KEY (crie no Google AI Studio).
Sem chave, o sistema funciona em MODO DEMONSTRAÇÃO, com uma análise de exemplo.
O modelo pode ser trocado pela variável GEMINI_MODEL (confira o nome atual na documentação do Google).
"""
import base64
import hashlib
import json
import os
import random
import re

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
# Tenta na ordem; se um nome de modelo não existir mais (erro 404), passa para o próximo.
MODELOS_PADRAO = ["gemini-flash-latest", "gemini-3.8-flash", "gemini-3.6-flash", "gemini-2.5-flash"]

PROMPT = """Você é um especialista em identificar alimentos em fotos de pratos de um restaurante \
self-service por quilo com churrascaria (Bovinu'S Grill & Beer, São Paulo). A foto é tirada \
de cima, com o prato em cima da balança.

PRIMEIRO, decida se a foto mostra um prato com comida.
Se for uma pessoa, um rosto, um objeto, uma tela, um prato vazio ou qualquer coisa que não seja \
comida servida: responda "e_prato_de_comida": false, "itens": [], "confianca_geral": 0 e, em \
"observacao", diga de forma genérica o que aparece (ex.: "A foto mostra uma pessoa, não um prato.").
Se uma pessoa estiver segurando o prato, analise apenas a comida.

SE FOR UM PRATO, identifique cada alimento VISÍVEL usando este guia visual do buffet:

Carnes do grill
- Picanha: fatias em meia-lua, rosadas ou vermelhas por dentro, com uma faixa grossa de gordura branca em uma das bordas.
- Fraldinha: fatias com fibras longas e paralelas bem marcadas, pouca gordura, cor mais escura.
- Maminha: fatias macias, fibras curtas, gordura fina na borda.
- Costela: pedaços escuros e caramelizados, com osso ou desfiados, gordura entremeada.
- Cupim: fatias marmorizadas, com aspecto gelatinoso e fibras irregulares.
- Linguiça: rodelas ou gomos cilíndricos com pele brilhante, interior rosado e granulado.
- Frango: coxa ou sobrecoxa com pele dourada, ou pedaços de carne branca.
- Coração de frango: pequenos, escuros, em formato de gota.
- Peixe: carne branca que se separa em lascas.

Acompanhamentos
- Arroz: grãos brancos (ou levemente amarelados), alongados e soltos, formando um monte claro.
- Feijão: grãos arredondados em caldo marrom (carioca) ou preto (feijão preto); o caldo costuma escorrer \
e manchar o arroz. Não confunda com molho de carne, que é liso e sem grãos.
- Farofa: farinha granulada e seca, amarelo-clara a dourada, às vezes com pedacinhos de bacon ou ovo.
- Batata frita: palitos amarelo-dourados.
- Mandioca: pedaços grandes, branco-amarelados e fibrosos.
- Macarrão: tiras ou tubos de massa, geralmente com molho.

Saladas
- Salada verde: folhas (alface, rúcula, agrião).
- Tomate: rodelas ou gomos vermelhos inteiros.
- Vinagrete: cubinhos de tomate, cebola e pimentão misturados, úmidos.
- Maionese: salada de batata cremosa e branca, com cubos.
- Legumes: cenoura, beterraba, brócolis, vagem e similares.

Pratos quentes e sobremesas
- Estrogonofe: molho cremoso bege-rosado com pedaços de carne ou frango.
- Lasanha: camadas de massa com molho e queijo gratinado.
- Pudim: creme amarelo com calda de caramelo.
- Mousse: creme aerado (chocolate ou maracujá).

Nomes que você deve usar quando o alimento corresponder: {itens}.
Para outros alimentos, use um nome curto em português.

REGRAS
1. Liste apenas o que dá para ver. Não invente alimentos escondidos.
2. "percentual" é a parte do PESO do prato, não da área. Carnes, feijão e arroz são densos; folhas \
ocupam muito espaço e pesam pouco. Os percentuais somam 100.
3. "confianca" (0 a 100) de cada item: use 90 ou mais só quando o alimento for inconfundível. \
Diminua quando estiver coberto por molho, misturado com outro, pequeno, escuro ou borrado.
4. "confianca_geral" (0 a 100): precisão do conjunto, considerando nitidez, luz, ângulo e alimentos sobrepostos.
5. "categoria": carne, acompanhamento, salada, quente, sobremesa ou outro.
6. "observacao": uma frase curta em português sobre o que atrapalhou ou ajudou a análise."""

SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "e_prato_de_comida": {"type": "BOOLEAN"},
        "confianca_geral": {"type": "NUMBER"},
        "observacao": {"type": "STRING"},
        "itens": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "nome": {"type": "STRING"},
                    "categoria": {"type": "STRING",
                                  "enum": ["carne", "acompanhamento", "salada", "quente", "sobremesa", "outro"]},
                    "percentual": {"type": "NUMBER"},
                    "confianca": {"type": "NUMBER"},
                },
                "required": ["nome", "categoria", "percentual", "confianca"],
            },
        },
    },
    "required": ["e_prato_de_comida", "confianca_geral", "observacao", "itens"],
}

MOTIVOS = {400: "pedido recusado, confira a chave", 401: "chave inválida", 403: "chave sem permissão",
           404: "modelo não encontrado", 429: "limite de uso atingido", 500: "erro no Google", 503: "Google indisponível"}


def tem_chave():
    return bool(os.environ.get("GEMINI_API_KEY"))


def modelos():
    escolhido = os.environ.get("GEMINI_MODEL")
    return [escolhido] if escolhido else MODELOS_PADRAO


def analisar(foto_bytes, mime, nomes_itens):
    """Devolve (analise, origem, aviso). origem = 'ia' ou 'demonstracao'."""
    if not tem_chave():
        return analise_demonstracao(foto_bytes, nomes_itens), "demonstracao", None
    try:
        return _chamar_gemini(foto_bytes, mime, nomes_itens), "ia", None
    except Exception as erro:  # a API falhou: segue em demonstração para não travar a balança
        status = getattr(getattr(erro, "response", None), "status_code", None)
        motivo = MOTIVOS.get(status, erro.__class__.__name__)
        print(f"[gemini] erro: {erro}")
        aviso = f"A IA não respondeu ({motivo}). Mostrando um resultado de exemplo."
        return analise_demonstracao(foto_bytes, nomes_itens), "demonstracao", aviso


def _corpo(foto_bytes, mime, nomes_itens, com_schema):
    config = {"responseMimeType": "application/json", "temperature": 0.1}
    if com_schema:
        config["responseSchema"] = SCHEMA
    return {
        "contents": [{"parts": [
            {"text": PROMPT.format(itens=", ".join(nomes_itens))},
            {"inlineData": {"mimeType": mime or "image/jpeg", "data": base64.b64encode(foto_bytes).decode()}},
        ]}],
        "generationConfig": config,
    }


def _chamar_gemini(foto_bytes, mime, nomes_itens):
    ultimo_erro = None
    for modelo in modelos():
        for com_schema in (True, False):
            resposta = requests.post(
                URL.format(modelo=modelo),
                headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                json=_corpo(foto_bytes, mime, nomes_itens, com_schema),
                timeout=45,
            )
            if resposta.status_code == 404:          # modelo não existe: tenta o próximo
                ultimo_erro = requests.HTTPError("404", response=resposta)
                break
            if resposta.status_code == 400 and com_schema:  # formato recusado: tenta sem o schema
                continue
            resposta.raise_for_status()
            texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
            return limpar_analise(json.loads(texto))
    raise ultimo_erro or RuntimeError("nenhum modelo respondeu")


def _numero(valor, padrao=0.0):
    """Converte 35, "35", "35%" ou "35,5" em número. Se não der, usa o padrão."""
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        return float(valor)
    achado = re.search(r"-?\d+(?:[.,]\d+)?", str(valor or ""))
    return float(achado.group().replace(",", ".")) if achado else padrao


def limpar_analise(analise):
    """Garante o formato esperado, mesmo se a IA responder de um jeito diferente."""
    if not isinstance(analise, dict) or not isinstance(analise.get("itens"), list):
        raise ValueError("resposta sem lista de itens")
    itens = []
    for item in analise["itens"]:
        if not isinstance(item, dict) or not str(item.get("nome") or "").strip():
            continue
        itens.append({
            "nome": str(item["nome"]).strip()[:60],
            "categoria": str(item.get("categoria") or "outro").strip().lower(),
            "percentual": _numero(item.get("percentual")),
            "confianca": _numero(item.get("confianca")),
        })
    return {
        "e_prato_de_comida": analise.get("e_prato_de_comida", True) is not False,
        "confianca_geral": _numero(analise.get("confianca_geral")),
        "observacao": str(analise.get("observacao") or "")[:300],
        "itens": itens,
    }


def analise_demonstracao(foto_bytes, nomes_itens):
    """Análise de exemplo, sem internet. A mesma foto sempre gera o mesmo resultado."""
    rnd = random.Random(int(hashlib.md5(foto_bytes or b"vazio").hexdigest(), 16))
    base = ["Picanha", "Arroz", "Feijão", "Salada verde", "Farofa", "Fraldinha", "Vinagrete", "Batata frita"]
    escolhidos = rnd.sample([n for n in base if n in nomes_itens], k=rnd.randint(4, 6))
    pesos = [rnd.uniform(0.6, 1.6) for _ in escolhidos]
    itens = [{
        "nome": nome,
        "categoria": "",
        "percentual": round(p * 100 / sum(pesos), 1),
        "confianca": rnd.randint(55, 97),
    } for nome, p in zip(escolhidos, pesos)]
    return {
        "e_prato_de_comida": True,
        "confianca_geral": rnd.randint(65, 90),
        "observacao": "",
        "itens": itens,
    }
