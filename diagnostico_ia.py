"""Diagnóstico da IA (Gemini) do Raio-X.

Rode na pasta do projeto:  python diagnostico_ia.py
Ele testa a sua conexão e a sua chave direto com o Google e mostra o que está acontecendo.
Copie tudo o que aparecer e envie para quem está ajudando no projeto (a chave NÃO é mostrada).
"""
import base64
import json
import os
import socket
import struct
import sys
import time
import zlib

import requests

import app  # noqa: F401  (carrega o .env)
from servicos import gemini

HOST = "generativelanguage.googleapis.com"


def linha(texto=""):
    print(texto, flush=True)


def imagem_teste():
    """PNG 256x256 bege (gerado aqui, sem bibliotecas extras)."""
    largura = altura = 256
    bruto = b"".join(b"\x00" + bytes([235, 225, 205]) * largura for _ in range(altura))

    def bloco(tipo, dados):
        return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", zlib.crc32(tipo + dados))
    return (b"\x89PNG\r\n\x1a\n" + bloco(b"IHDR", struct.pack(">IIBBBBB", largura, altura, 8, 2, 0, 0, 0))
            + bloco(b"IDAT", zlib.compress(bruto)) + bloco(b"IEND", b""))


linha("=== Diagnóstico da IA do Raio-X ===")
linha(f"Python {sys.version.split()[0]} | requests {requests.__version__}")
chave = os.environ.get("GEMINI_API_KEY", "")
linha(f"1. Chave no .env: {'OK (' + str(len(chave)) + ' caracteres)' if chave else 'NÃO ENCONTRADA'}")
if not chave:
    sys.exit("   Cole a chave no arquivo .env (GEMINI_API_KEY=...) e rode de novo.")

proxy = {k: v for k, v in os.environ.items() if k.lower() in ("http_proxy", "https_proxy")}
linha(f"   Proxy configurado: {proxy or 'nenhum'}")

t = time.monotonic()
try:
    socket.create_connection((HOST, 443), timeout=10).close()
    linha(f"2. Conexão com o Google: OK ({time.monotonic() - t:.1f} s)")
except Exception as erro:
    linha(f"2. Conexão com o Google: FALHOU ({erro.__class__.__name__}: {erro})")
    linha("   A rede está bloqueando o Google. Teste em outra rede (ex.: roteador do celular).")
    sys.exit(1)

t = time.monotonic()
r = requests.get(f"https://{HOST}/v1beta/models", headers={"x-goog-api-key": chave},
                 params={"pageSize": 1000}, timeout=20)
linha(f"3. Lista de modelos: HTTP {r.status_code} ({time.monotonic() - t:.1f} s)")
if r.status_code != 200:
    linha(f"   Resposta: {r.text[:400]}")
    sys.exit("   A chave foi recusada. Confira se copiou a chave inteira no .env.")
nomes = sorted(m["name"].split("/", 1)[1] for m in r.json().get("models", [])
               if "generateContent" in m.get("supportedGenerationMethods", []))
flash = [n for n in nomes if "flash" in n]
linha(f"   Modelos 'flash' disponíveis: {', '.join(flash) or 'nenhum'}")
linha(f"   O Raio-X vai tentar, nesta ordem: {', '.join(gemini.modelos())}")

linha("4. Teste de velocidade (imagem pequena). Pode levar alguns minutos, aguarde o 'Fim'.")
candidatos = []
for m in gemini.modelos() + ["gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-2.5-flash-lite"]:
    if m not in candidatos and (not nomes or m in nomes):
        candidatos.append(m)
for modelo in candidatos[:6]:
    for nivel, nome_nivel in ((0, "pensando pouco"), (2, "simples")):
        print(f"   {modelo:26} {nome_nivel:15} testando...", end=" ", flush=True)
        corpo = gemini._corpo(imagem_teste(), "image/png", ["Arroz", "Feijão"], modelo, nivel)
        t = time.monotonic()
        try:
            resp = requests.post(gemini.URL.format(modelo=modelo), headers={"x-goog-api-key": chave},
                                 json=corpo, timeout=60)
            dt = time.monotonic() - t
            if resp.status_code == 200:
                texto = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
                json.loads(texto)
                print(f"OK em {dt:.1f} s", flush=True)
                break
            print(f"HTTP {resp.status_code} em {dt:.1f} s: {resp.text[:150]}", flush=True)
        except Exception as erro:
            print(f"FALHOU em {time.monotonic() - t:.1f} s ({erro.__class__.__name__})", flush=True)
linha("\nFim. Copie tudo acima e envie.")
