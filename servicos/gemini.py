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

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
MODELO_PADRAO = "gemini-2.5-flash"

PROMPT = """Você é um especialista em identificar alimentos em fotos de pratos de um restaurante \
self-service por quilo com churrascaria (Bovinu'S, São Paulo).

Analise a foto e identifique CADA alimento visível no prato.
Itens comuns no buffet: {itens}.
Use exatamente um desses nomes quando o alimento corresponder; se for outro alimento, use um nome curto em português.

Para cada alimento, informe:
- "nome": nome do alimento
- "categoria": uma entre carne, acompanhamento, salada, quente, sobremesa, outro
- "percentual": quanto do PESO do prato esse alimento representa (todos somando 100)
- "confianca": de 0 a 100, o quanto você tem certeza de que identificou esse alimento corretamente

Informe também:
- "confianca_geral": de 0 a 100, a precisão geral da análise (considere nitidez, iluminação, \
alimentos sobrepostos ou escondidos)
- "e_prato_de_comida": true ou false
- "observacao": uma frase curta em português sobre a qualidade da foto ou algo que atrapalhou

Responda SOMENTE com JSON neste formato:
{{"e_prato_de_comida": true, "confianca_geral": 80, "observacao": "...",
 "itens": [{{"nome": "Picanha", "categoria": "carne", "percentual": 35, "confianca": 90}}]}}"""


def tem_chave():
    return bool(os.environ.get("GEMINI_API_KEY"))


def analisar(foto_bytes, mime, nomes_itens):
    """Devolve (analise, origem, aviso). origem = 'ia' ou 'demonstracao'."""
    if not tem_chave():
        return analise_demonstracao(foto_bytes, nomes_itens), "demonstracao", None
    try:
        return _chamar_gemini(foto_bytes, mime, nomes_itens), "ia", None
    except Exception as erro:  # a API falhou: segue em demonstração para não travar a balança
        aviso = f"A IA não respondeu ({erro.__class__.__name__}). Mostrando análise de demonstração."
        print(f"[gemini] erro: {erro}")
        return analise_demonstracao(foto_bytes, nomes_itens), "demonstracao", aviso


def _chamar_gemini(foto_bytes, mime, nomes_itens):
    modelo = os.environ.get("GEMINI_MODEL", MODELO_PADRAO)
    corpo = {
        "contents": [{"parts": [
            {"text": PROMPT.format(itens=", ".join(nomes_itens))},
            {"inline_data": {"mime_type": mime or "image/jpeg",
                             "data": base64.b64encode(foto_bytes).decode()}},
        ]}],
        "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2},
    }
    resposta = requests.post(
        URL.format(modelo=modelo),
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json=corpo,
        timeout=45,
    )
    resposta.raise_for_status()
    texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
    analise = json.loads(texto)
    if not isinstance(analise.get("itens"), list):
        raise ValueError("resposta sem lista de itens")
    return analise


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
        "observacao": "Modo demonstração: configure a chave do Gemini para analisar a foto de verdade.",
        "itens": itens,
    }
