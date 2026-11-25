"""Análise da foto do prato com a API do Google Gemini.

Configure a chave na variável de ambiente GEMINI_API_KEY (crie no Google AI Studio).
Sem chave, nenhuma foto é analisada. Para ensaiar sem internet, use RAIOX_DEMO=1 (resultado de exemplo).
O modelo pode ser trocado pela variável GEMINI_MODEL (confira o nome atual na documentação do Google).
"""
import base64
import hashlib
import json
import os
import random
import re
import time

import requests

URL = "https://generativelanguage.googleapis.com/v1beta/models/{modelo}:generateContent"
# Tenta na ordem; se um nome de modelo não existir mais (erro 404), passa para o próximo.
MODELOS_PADRAO = [
    # rápidos primeiro: na balança, responder em segundos vale mais que o modelo maior
    "gemini-flash-lite-latest", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite", "gemini-2.5-flash-lite",
    "gemini-3.8-flash", "gemini-flash-latest", "gemini-2.5-flash",
]
ESPERA_SEGUNDOS = 1.5   # pausa antes de tentar de novo quando o Google está ocupado
TEMPO_POR_TENTATIVA = 25  # segundos para um modelo responder antes de passar ao próximo
TEMPO_MAXIMO = 90         # segundos, somando todas as tentativas

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
           404: "modelo não encontrado", 429: "limite de uso atingido", 500: "erro no Google", 503: "Google sobrecarregado no momento"}


def tem_chave():
    return bool(os.environ.get("GEMINI_API_KEY"))


def demo_ligado():
    """Resultado de exemplo só quando pedido de propósito (ex.: ensaio do pitch sem internet)."""
    return os.environ.get("RAIOX_DEMO", "").strip() in ("1", "sim", "true")


_disponiveis = None


def modelos_disponiveis():
    """Pergunta ao Google (uma vez) quais modelos esta chave pode usar. Se falhar, devolve None."""
    global _disponiveis
    if _disponiveis is None:
        try:
            r = requests.get("https://generativelanguage.googleapis.com/v1beta/models",
                             headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                             params={"pageSize": 1000}, timeout=10)
            r.raise_for_status()
            _disponiveis = {m["name"].split("/", 1)[1] for m in r.json().get("models", [])
                            if "generateContent" in m.get("supportedGenerationMethods", [])}
        except Exception as erro:
            print(f"[gemini] não consegui listar os modelos ({erro.__class__.__name__}); usando a lista padrão")
            _disponiveis = set()
    return _disponiveis


def modelos():
    escolhido = os.environ.get("GEMINI_MODEL")
    if escolhido:
        return [escolhido]
    disponiveis = modelos_disponiveis()
    if not disponiveis:
        return MODELOS_PADRAO
    lista = [m for m in MODELOS_PADRAO if m in disponiveis]
    # se nenhum da lista existir, usa qualquer "flash" que a chave tenha (exceto imagem/áudio/tts)
    extras = sorted((m for m in disponiveis if "flash" in m and not any(
        x in m for x in ("image", "tts", "audio", "live", "embedding", "omni", "preview"))),
        key=lambda m: ("lite" not in m, m), reverse=False)
    return (lista + [m for m in extras if m not in lista])[:6] or MODELOS_PADRAO


def analisar(foto_bytes, mime, nomes_itens):
    """Devolve (analise, origem, aviso).
    origem = 'ia', 'demonstracao' ou 'erro'. Em 'erro', analise é None e nada é inventado."""
    if not tem_chave():
        if demo_ligado():
            return analise_demonstracao(foto_bytes, nomes_itens), "demonstracao", None
        return None, "erro", ("A IA está desligada, então a foto não foi analisada. "
                              "Configure a chave do Gemini (GEMINI_API_KEY) e reinicie o servidor.")
    try:
        return _chamar_gemini(foto_bytes, mime, nomes_itens), "ia", None
    except Exception as erro:
        status = getattr(getattr(erro, "response", None), "status_code", None)
        motivo = MOTIVOS.get(status) or ("o Google demorou demais para responder"
                                         if isinstance(erro, requests.Timeout) else erro.__class__.__name__)
        print(f"[gemini] erro: {erro}")
        if demo_ligado():
            return (analise_demonstracao(foto_bytes, nomes_itens), "demonstracao",
                    f"A IA não respondeu ({motivo}). Mostrando um resultado de exemplo.")
        return None, "erro", f"A IA não conseguiu analisar a foto ({motivo}). Tente de novo."


def _config_pensamento(modelo):
    """Pede para o modelo pensar pouco: a resposta sai bem mais rápido.
    Gemini 3 usa 'thinkingLevel'; Gemini 2.5 usa 'thinkingBudget'."""
    if "2.5" in modelo:
        return {"thinkingBudget": 0}
    if "lite" in modelo:
        return None
    return {"thinkingLevel": "low"}


def _corpo(foto_bytes, mime, nomes_itens, modelo, nivel):
    """nivel 0: completo (schema + pensar pouco); 1: sem a config de pensamento; 2: sem schema."""
    config = {"responseMimeType": "application/json", "temperature": 0.1}
    if nivel <= 1:
        config["responseSchema"] = SCHEMA
    pensamento = _config_pensamento(modelo)
    if nivel == 0 and pensamento:
        config["thinkingConfig"] = pensamento
    return {
        "contents": [{"parts": [
            {"text": PROMPT.format(itens=", ".join(nomes_itens))},
            {"inlineData": {"mimeType": mime or "image/jpeg", "data": base64.b64encode(foto_bytes).decode()}},
        ]}],
        "generationConfig": config,
    }


OCUPADO = (500, 502, 503, 504)   # Google sobrecarregado ou instável: vale tentar de novo


def _chamar_gemini(foto_bytes, mime, nomes_itens):
    """Tenta cada modelo da lista. Se o Google estiver ocupado, espera um pouco, tenta de novo
    e depois passa para o próximo modelo. Só desiste quando nenhum responder."""
    ultimo_erro = None
    inicio = time.monotonic()
    for modelo in modelos():
        if time.monotonic() - inicio > TEMPO_MAXIMO:   # não deixa a balança esperando demais
            print("[gemini] tempo total esgotado, desistindo")
            break
        nivel = 0
        tentativas_ocupado = 0
        while True:
            try:
                resposta = requests.post(
                    URL.format(modelo=modelo),
                    headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
                    json=_corpo(foto_bytes, mime, nomes_itens, modelo, nivel),
                    timeout=max(5, min(TEMPO_POR_TENTATIVA, TEMPO_MAXIMO - (time.monotonic() - inicio))),
                )
            except requests.Timeout as erro:   # demorou demais: tenta o próximo modelo
                ultimo_erro = erro
                print(f"[gemini] {modelo}: não respondeu em {int(time.monotonic() - inicio)} s, tentando outro modelo")
                break
            if resposta.status_code == 404:       # modelo não existe: próximo
                ultimo_erro = requests.HTTPError("404", response=resposta)
                print(f"[gemini] {modelo}: modelo não encontrado, tentando outro")
                break
            if resposta.status_code == 400 and nivel < 2:   # opção não aceita por este modelo: simplifica
                print(f"[gemini] {modelo}: pedido recusado (400), tentando versão mais simples")
                nivel += 1
                continue
            if resposta.status_code in OCUPADO:
                ultimo_erro = requests.HTTPError(str(resposta.status_code), response=resposta)
                tentativas_ocupado += 1
                if tentativas_ocupado <= 1:        # espera e tenta o mesmo modelo mais uma vez
                    print(f"[gemini] {modelo}: Google ocupado ({resposta.status_code}), tentando de novo")
                    time.sleep(ESPERA_SEGUNDOS)
                    continue
                print(f"[gemini] {modelo}: continua ocupado, tentando outro modelo")
                break
            resposta.raise_for_status()           # 401, 403, 429...: erro definitivo
            texto = resposta.json()["candidates"][0]["content"]["parts"][0]["text"]
            print(f"[gemini] {modelo} respondeu em {time.monotonic() - inicio:.1f} s")
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
