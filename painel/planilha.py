"""Respostas da pesquisa (Google Forms -> Google Planilhas) para o banco do painel.

O painel baixa a planilha sozinho a cada 2 minutos (e pelo botão "Sincronizar agora").
Cada linha vira uma avaliação; a mesma linha nunca é importada duas vezes.

Configuração: variável PLANILHA_AVALIACOES com o link da planilha (o de "Editar" serve).
A planilha precisa estar em "Qualquer pessoa com o link pode ver" para o painel conseguir ler.
Para desligar a sincronização: PLANILHA_AVALIACOES=desligado

Também dá para importar um CSV baixado à mão:
    python -m painel.planilha respostas.csv
    python -m painel.planilha            (baixa da planilha configurada)
"""
import csv
import hashlib
import io
import os
import re
import sys
import threading
import time
import urllib.request
from datetime import datetime

from . import banco, eventos

PLANILHA_PADRAO = ("https://docs.google.com/spreadsheets/d/1XTmWoDvZiKXfRDBuAWlE5j5tTUdJ3kxGXqxXPjlmr0s/"
                   "edit?gid=1675468231#gid=1675468231")
INTERVALO_S = 120
TIMEOUT_S = 15

# Pergunta do formulário -> campo do banco. A ORDEM importa: a 1ª regra que casar vence.
# (ex.: "O que não estava bom nesses itens?" precisa casar com motivo antes de nao_gostou)
REGRAS = [
    ("carimbo", "criada_em"), ("timestamp", "criada_em"),
    ("o que nao estava bom", "motivo"), ("motivo", "motivo"),
    ("item nao estava bom", "nao_gostou"), ("nao gostou", "nao_gostou"),
    ("mais gostou", "gostou"),
    ("limpeza", "nota_limpeza"),
    ("comida", "nota_comida"),
    ("espera", "nota_espera"),
    ("contar mais", "comentario"), ("coment", "comentario"), ("sugest", "comentario"),
    ("comanda", "codigo_comanda"),
    ("mesa", "mesa"),
    ("cashback", "beneficio"), ("desconto", "beneficio"), ("benef", "beneficio"),
]

_trava = threading.Lock()
_estado = {"ultima": None, "ok": None, "mensagem": "Ainda não sincronizou.", "novas": 0, "linhas": 0}


def url_planilha():
    url = os.environ.get("PLANILHA_AVALIACOES", PLANILHA_PADRAO).strip()
    return None if url.lower() in ("", "0", "desligado", "nao") else url


def url_csv(url):
    """Link de edição/visualização -> link de exportação em CSV da mesma aba."""
    if "format=csv" in url or url.lower().endswith(".csv"):
        return url
    achado = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url)
    if not achado:
        raise ValueError("Link da planilha não reconhecido.")
    gid = re.search(r"[#&?]gid=(\d+)", url)
    return (f"https://docs.google.com/spreadsheets/d/{achado.group(1)}/export?format=csv"
            + (f"&gid={gid.group(1)}" if gid else ""))


def campo_da_pergunta(pergunta):
    texto = eventos._sem_acento(pergunta)
    return next((campo for trecho, campo in REGRAS if trecho in texto), None)


def _data(texto):
    texto = (texto or "").strip()
    for formato in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S"):
        try:
            return datetime.strptime(texto, formato)
        except ValueError:
            pass
    return None


def importar_texto(con, texto_csv):
    """Importa o conteúdo CSV. Devolve (novas, repetidas, erros, campos reconhecidos)."""
    leitor = csv.reader(io.StringIO(texto_csv.lstrip("﻿")))
    cabecalho = next(leitor, [])
    campos = [campo_da_pergunta(c) for c in cabecalho]
    novas = repetidas = 0
    erros = []
    for n, linha in enumerate(leitor, start=2):
        if not any(c.strip() for c in linha):
            continue
        dados = {}
        for campo, valor in zip(campos, linha):
            if campo and valor.strip() and campo not in dados:
                dados[campo] = valor.strip()
        carimbo = dados.get("criada_em", "")
        dados["criada_em"] = _data(carimbo)
        dados["origem"] = "planilha"
        # a chave é o carimbo de data/hora da resposta: se alguém corrigir uma célula, não vira resposta nova
        dados["chave_origem"] = hashlib.sha1((carimbo or "\x1f".join(linha)).encode("utf-8")).hexdigest()
        if con.execute("SELECT 1 FROM avaliacoes WHERE chave_origem = ?", (dados["chave_origem"],)).fetchone():
            repetidas += 1
            continue
        try:
            eventos.registrar_avaliacao(con, dados)
            novas += 1
        except (ValueError, TypeError) as erro:
            erros.append(f"linha {n}: {erro}")
    con.commit()
    reconhecidos = {c: f for c, f in zip(cabecalho, campos) if f}
    return novas, repetidas, erros, reconhecidos


def baixar(url):
    req = urllib.request.Request(url_csv(url), headers={"User-Agent": "PainelBovinus/1.0"})
    with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
        tipo = resp.headers.get("Content-Type", "")
        corpo = resp.read().decode("utf-8", "replace")
    if "text/csv" not in tipo and not corpo.lower().startswith(("carimbo", "timestamp", "﻿carimbo")):
        raise ValueError("A planilha não está pública. Em Compartilhar, use 'Qualquer pessoa com o link: Leitor'.")
    return corpo


def sincronizar(caminho_banco=None):
    """Baixa a planilha e importa as respostas novas. Nunca derruba o painel: sem internet só avisa."""
    url = url_planilha()
    if not url:
        _estado.update(ok=None, mensagem="Sincronização com a planilha desligada.")
        return dict(_estado)
    with _trava:
        try:
            texto = baixar(url)
            con = banco.conectar(caminho_banco)
            try:
                banco.criar_tabelas(con)
                novas, repetidas, erros, _ = importar_texto(con, texto)
                total = con.execute("SELECT COUNT(*) FROM avaliacoes WHERE origem = 'planilha'").fetchone()[0]
            finally:
                con.close()
            msg = f"{novas} resposta(s) nova(s)" if novas else "Nenhuma resposta nova"
            if erros:
                msg += f"; {len(erros)} linha(s) com erro: " + "; ".join(erros[:3])
            _estado.update(ultima=datetime.now().strftime(banco.FORMATO), ok=not erros, mensagem=msg,
                           novas=novas, linhas=total)
        except Exception as erro:  # sem internet, planilha privada etc.
            _estado.update(ultima=datetime.now().strftime(banco.FORMATO), ok=False,
                           mensagem=f"Não foi possível ler a planilha ({erro.__class__.__name__}): "
                                    f"{str(erro)[:150]}. Os dados já importados continuam no painel.")
    return dict(_estado)


def estado():
    return dict(_estado, configurada=bool(url_planilha()))


def iniciar_sincronizacao_automatica():
    """Thread em segundo plano: sincroniza logo ao abrir e depois a cada INTERVALO_S."""
    if not url_planilha() or os.environ.get("PAINEL_SINCRONIZAR") == "0":
        return None

    def laco():
        while True:
            sincronizar()
            time.sleep(INTERVALO_S)

    t = threading.Thread(target=laco, name="sincroniza-planilha", daemon=True)
    t.start()
    return t


def main():
    con = banco.conectar()
    banco.criar_tabelas(con)
    if len(sys.argv) > 1 and not sys.argv[1].startswith("http"):
        with open(sys.argv[1], encoding="utf-8-sig", newline="") as f:
            texto = f.read()
    else:
        texto = baixar(sys.argv[1] if len(sys.argv) > 1 else url_planilha())
    novas, repetidas, erros, campos = importar_texto(con, texto)
    print("Perguntas reconhecidas:")
    for pergunta, campo in campos.items():
        print(f"  {pergunta.strip()[:60]:<60} -> {campo}")
    print(f"{novas} resposta(s) importada(s), {repetidas} já estavam no banco.")
    for e in erros[:20]:
        print("  ", e)


if __name__ == "__main__":
    main()
