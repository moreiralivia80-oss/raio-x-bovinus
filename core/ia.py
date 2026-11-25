"""Integração com a IA (Google Gemini) + modo demo.

Modo demo: funciona sem internet e sem chave (útil para desenvolver e como plano B no pitch).
Modo IA:   defina GEMINI_API_KEY em .streamlit/secrets.toml ou como variável de ambiente.
Confira na documentação do Google AI Studio o nome do modelo atual com suporte a imagens.
"""
import base64
import hashlib
import json
import os
import random

import requests

MODELO_PADRAO = "gemini-2.5-flash"
URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
ASSUNTOS = ["comida", "espera", "limpeza", "atendimento", "outro"]


def obter_chave():
    """Procura a chave em st.secrets e depois nas variáveis de ambiente."""
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"], st.secrets.get("GEMINI_MODEL", MODELO_PADRAO)
    except Exception:
        pass
    return os.environ.get("GEMINI_API_KEY"), os.environ.get("GEMINI_MODEL", MODELO_PADRAO)


def _chamar_gemini(partes, chave, modelo):
    corpo = {"contents": [{"parts": partes}],
             "generationConfig": {"response_mime_type": "application/json", "temperature": 0.2}}
    resp = requests.post(URL.format(modelo=modelo), params={"key": chave}, json=corpo, timeout=40)
    resp.raise_for_status()
    texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    return json.loads(texto)


# ---------- Módulo 1: analisar foto do prato ----------

def analisar_prato(foto_bytes, mime, nomes_itens):
    """Devolve (composicao {item: %}, origem 'ia' ou 'demo', mensagem_de_erro ou None)."""
    chave, modelo = obter_chave()
    if chave and foto_bytes:
        try:
            prompt = (
                "Você analisa fotos de pratos de um restaurante self-service por quilo com churrasco. "
                f"Itens possíveis do buffet: {', '.join(nomes_itens)}. "
                "Estime a proporção aproximada do PESO do prato ocupada por cada item visível. "
                "Use somente nomes da lista. Responda apenas JSON no formato "
                '{"itens": [{"nome": "Picanha", "percentual": 35}]}, com percentuais somando 100.'
            )
            dados = _chamar_gemini(
                [{"text": prompt},
                 {"inline_data": {"mime_type": mime or "image/jpeg",
                                  "data": base64.b64encode(foto_bytes).decode()}}],
                chave, modelo)
            return {i["nome"]: float(i["percentual"]) for i in dados.get("itens", [])}, "ia", None
        except Exception as erro:
            return composicao_demo(foto_bytes, nomes_itens), "demo", str(erro)
    return composicao_demo(foto_bytes, nomes_itens), "demo", None


def composicao_demo(foto_bytes, nomes_itens, categorias=None):
    """Composição plausível e determinística (a mesma foto gera o mesmo resultado)."""
    rnd = random.Random(int(hashlib.md5(foto_bytes or b"vazio").hexdigest(), 16))
    escolhidos = rnd.sample(list(nomes_itens), k=min(len(nomes_itens), rnd.randint(4, 7)))
    pesos = [rnd.random() + 0.2 for _ in escolhidos]
    return {n: p * 100 / sum(pesos) for n, p in zip(escolhidos, pesos)}


# ---------- Módulo 2: classificar comentário ----------

PALAVRAS = {
    "espera": ["fila", "demor", "espera", "esperar", "lento"],
    "limpeza": ["suj", "limp", "mesa"],
    "atendimento": ["garçom", "garcom", "atend", "educad", "grosso"],
    "comida": ["frio", "fria", "salgad", "gostos", "carne", "sabor", "comida", "cru", "seco"],
}


def classificar_comentario(texto):
    """Devolve o assunto do comentário. Usa a IA se houver chave; senão, palavras-chave."""
    if not texto or not texto.strip():
        return None
    chave, modelo = obter_chave()
    if chave:
        try:
            prompt = ("Classifique o comentário de um cliente de restaurante em UM assunto entre "
                      f"{ASSUNTOS}. Responda apenas JSON: {{\"assunto\": \"...\"}}. Comentário: {texto}")
            assunto = _chamar_gemini([{"text": prompt}], chave, modelo).get("assunto", "outro")
            return assunto if assunto in ASSUNTOS else "outro"
        except Exception:
            pass
    t = texto.lower()
    for assunto, palavras in PALAVRAS.items():
        if any(p in t for p in palavras):
            return assunto
    return "outro"
