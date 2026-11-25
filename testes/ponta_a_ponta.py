r"""Teste de ponta a ponta: chama o painel RODANDO, como os aparelhos do salão fariam.

Use um banco vazio separado (nunca o do restaurante) e a planilha desligada:

    $env:BOVINUS_DB="C:\temp\teste.db"; $env:PLANILHA_AVALIACOES="desligado"
    .\executavel\PainelBovinus.exe --vazio --sem-navegador --porta 5090
    python testes\ponta_a_ponta.py http://127.0.0.1:5090 C:\temp\teste.db

"OK" = comportamento esperado; "FALHA" = problema conhecido ou novo; "INFO" = comportamento a observar.
"""
import json
import sqlite3
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from http.cookiejar import CookieJar

BASE, DB = sys.argv[1], sys.argv[2]
achados = []


def chamar(metodo, rota, corpo=None, form=None, abridor=None, seguir=True):
    dados, cab = None, {}
    if corpo is not None:
        dados, cab = json.dumps(corpo).encode(), {"Content-Type": "application/json"}
    if form is not None:
        dados, cab = urllib.parse.urlencode(form).encode(), {"Content-Type": "application/x-www-form-urlencoded"}
    req = urllib.request.Request(BASE + rota, data=dados, headers=cab, method=metodo)
    op = abridor or urllib.request.build_opener()
    if not seguir:
        class SemRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        op = urllib.request.build_opener(SemRedirect, *(h for h in (abridor.handlers if abridor else [])
                                                         if isinstance(h, urllib.request.HTTPCookieProcessor)))
    try:
        r = op.open(req, timeout=20)
        return r.status, r.read().decode("utf-8", "replace"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace"), dict(e.headers)


def j(t):
    try:
        return json.loads(t)
    except ValueError:
        return t


def ok(nome, cond, detalhe=""):
    print(("  OK   " if cond else "  FALHA") + f"  {nome}" + (f"  -> {detalhe}" if detalhe and not cond else ""))
    if not cond:
        achados.append(f"{nome}: {detalhe}")


def info(nome, valor):
    print(f"  INFO   {nome}: {valor}")


def db(sql, *p):
    con = sqlite3.connect(DB)
    try:
        return con.execute(sql, p).fetchall()
    finally:
        con.close()


def pip(codigo, tipo, **extra):
    s, t, _ = chamar("POST", "/api/comanda/pipar", {"codigo": codigo, "tipo": tipo, **extra})
    return s, j(t)


agora = datetime.now()
ts = lambda m: (agora - timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S")  # noqa: E731

print("\n[1] Gerente: acesso e login (banco vazio)")
ok("tela de login abre", chamar("GET", "/painel/login")[0] == 200)
ok("/painel sem login redireciona", chamar("GET", "/painel", seguir=False)[0] in (301, 302))
ok("API de dados sem login = 401", chamar("GET", "/api/painel/dados")[0] == 401)
ok("CSV sem login = 401", chamar("GET", "/api/painel/exportar/avaliacoes.csv")[0] == 401)
ok("senha errada = 401", chamar("POST", "/painel/login", form={"usuario": "gerente", "senha": "x"})[0] == 401)
jar = CookieJar()
gerente = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
s, _, h = chamar("POST", "/painel/login?proximo=//site-externo.com", form={"usuario": "gerente", "senha": "bovinus2026"},
                 abridor=gerente, seguir=False)
ok("login certo redireciona", s in (301, 302))
ok("redirecionamento externo bloqueado", "site-externo" not in h.get("Location", ""), h.get("Location"))
for dias in (1, 7, 30, 0, 999):
    s, t, _ = chamar("GET", f"/api/painel/dados?dias={dias}", abridor=gerente)
    ok(f"painel vazio dias={dias}", s == 200 and "resumo" in j(t), t[:120])
s, t, _ = chamar("GET", "/api/painel/dados?dias=abc", abridor=gerente)
ok("dias inválido não quebra", s == 200, t[:80])
d = j(chamar("GET", "/api/painel/dados?dias=7", abridor=gerente)[1])
ok("banco vazio: sem alertas e margem vazia", d["alertas"] == [] and d["resumo"]["margem"] is None, d["alertas"])
for nome in ("vw_jornada_cliente", "vw_tempo_mesa_suja", "vw_pratos", "vw_mix_itens", "vw_opiniao_itens",
             "avaliacoes", "itens_buffet", "comandas", "eventos_comanda", "pratos", "itens_prato", "limpezas_mesa",
             "avaliacao_itens", "mesas"):
    s, t, h = chamar("GET", f"/api/painel/exportar/{nome}.csv", abridor=gerente)
    ok(f"CSV {nome}", s == 200 and t.startswith("﻿"), s)
ok("CSV fora da lista = 404", chamar("GET", "/api/painel/exportar/sqlite_master.csv", abridor=gerente)[0] == 404)
ok("CSV com ../ = 404", chamar("GET", "/api/painel/exportar/..%2Fmeta.csv", abridor=gerente)[0] == 404)
s, t, _ = chamar("GET", "/api/mesas")
ok("90 mesas livres", s == 200 and len(j(t)) == 90 and all(m["status"] == "livre" for m in j(t)))

print("\n[2] Jornada completa de 1 cliente")
s, r = pip("100", "entrada", momento=ts(50))
ok("entrada", s == 201)
s, r = pip("100", "balanca", momento=ts(41))
ok("balança mede 9 min", s == 201 and r.get("minutos_desde_entrada") == 9.0, r)
s, r = pip("100", "atendimento_mesa", mesa=12, momento=ts(38))
ok("garçom liga comanda à mesa 12", s == 201)
s, r = pip("100", "pagamento", momento=ts(5))
ok("pagamento deixa mesa 12 suja sozinha", s == 201 and r.get("mesa_suja", {}).get("mesa") == 12, r)
s, t, _ = chamar("POST", "/api/mesas/12/limpa")
ok("limpa mede ~5 min", s == 200 and 4 <= j(t).get("minutos_suja", 0) <= 6, t)
row = db("SELECT min_ate_pesar, min_ate_atendimento_mesa, min_permanencia FROM vw_jornada_cliente WHERE codigo='100'")
ok("view da jornada (9 / 3 / 45 min)", row == [(9.0, 3.0, 45.0)], row)

print("\n[3] Erros de operação na estação de pip")
ok("tipo inválido = 400", pip("1", "xx")[0] == 400)
ok("código vazio = 400", pip("  ", "entrada")[0] == 400)
ok("mesa inexistente = 400", pip("1", "atendimento_mesa", mesa=999)[0] == 400)
ok("mesa com letras = 400", pip("1", "atendimento_mesa", mesa="abc")[0] == 400)
ok("garçom sem mesa = 400", pip("1", "atendimento_mesa")[0] == 400)
s1 = pip("700", "entrada", id_cliente="toque-1")[0]
s2 = pip("700", "entrada", id_cliente="toque-1", momento=ts(-5))[0]
ok("reenvio da fila offline (mesmo id) não duplica", (s1, s2) == (201, 200), (s1, s2))
s, t, _ = chamar("POST", "/api/comanda/pipar", corpo=None, form={"codigo": "2", "tipo": "entrada"})
ok("aceita formulário além de JSON", s == 201)
s, t, _ = chamar("POST", "/api/comanda/pipar", corpo={"codigo": "3", "tipo": "entrada", "momento": "ontem"})
ok("momento inválido = 400 (não 500)", s == 400, f"status {s}")

print("\n[4] Leitura dupla (leitor de código de barras repete)")
antes = db("SELECT COUNT(*) FROM comandas")[0][0]
pip("200", "entrada"); pip("200", "entrada")
depois = db("SELECT COUNT(*) FROM comandas")[0][0]
ok("entrada pipada 2x cria 1 comanda", depois - antes == 1, f"criou {depois - antes} comandas")
pip("200", "balanca"); pip("200", "balanca")
n = db("SELECT qtd_pesagens FROM vw_jornada_cliente WHERE codigo='200' ORDER BY comanda_id DESC LIMIT 1")
ok("balança pipada 2x em segundos = 1 pesagem", n and n[0][0] == 1, f"pesagens={n}")
pip("200", "pagamento")
antes = db("SELECT COUNT(*) FROM comandas")[0][0]
pip("200", "pagamento")
depois = db("SELECT COUNT(*) FROM comandas")[0][0]
ok("pagamento pipado 2x não cria comanda fantasma", depois == antes, f"criou {depois - antes} comanda(s) só com pagamento")

print("\n[5] Grupo na mesma mesa")
pip("301", "entrada", momento=ts(60)); pip("302", "entrada", momento=ts(60))
pip("301", "atendimento_mesa", mesa=20, momento=ts(45)); pip("302", "atendimento_mesa", mesa=20, momento=ts(45))
s, r = pip("301", "pagamento", momento=ts(10))
ok("1º do grupo paga: mesa NÃO fica suja", "mesa_suja" not in r, r)
s, r = pip("302", "pagamento", momento=ts(8))
ok("último paga: mesa fica suja", r.get("mesa_suja", {}).get("mesa") == 20, r)
chamar("POST", "/api/mesas/20/limpa")
pip("401", "entrada", momento=ts(60)); pip("402", "entrada", momento=ts(60))
pip("401", "atendimento_mesa", mesa=21, momento=ts(45))  # garçom pipou só quem pediu bebida
s, r = pip("401", "pagamento", momento=ts(10))
info("garçom pipou só 1 comanda do grupo", "mesa 21 marcada suja com o colega ainda sentado" if r.get("mesa_suja") else "ok")
chamar("POST", "/api/mesas/21/limpa")

print("\n[6] Mesas (tela do garçom)")
ok("limpa sem estar suja não quebra", j(chamar("POST", "/api/mesas/30/limpa")[1]).get("estava_suja") is False)
chamar("POST", "/api/mesas/30/saiu"); r = j(chamar("POST", "/api/mesas/30/saiu")[1])
ok("toque duplo em 'saiu' não duplica", r.get("ja_estava_suja") is True)
chamar("POST", "/api/mesas/30/limpa")
ok("mesa 999 saiu = 400", chamar("POST", "/api/mesas/999/saiu")[0] == 400, chamar("POST", "/api/mesas/999/saiu")[0])
chamar("POST", "/api/mesas/31/saiu")
ok("desfazer volta a mesa para livre", j(chamar("POST", "/api/mesas/31/desfazer")[1]).get("status") == "livre")
# garçom esquece de tocar "limpa" (mesa suja desde ontem)
chamar("POST", "/api/mesas/40/saiu", {"momento": (agora - timedelta(hours=20)).strftime("%Y-%m-%d %H:%M:%S")})
m = [x for x in j(chamar("GET", "/api/mesas")[1]) if x["numero"] == 40][0]
info("mesa esquecida suja desde ontem", f"aparece suja há {m['minutos']} min")
pip("500", "entrada"); s, r = pip("500", "atendimento_mesa", mesa=40)
m = [x for x in j(chamar("GET", "/api/mesas")[1]) if x["numero"] == 40][0]
ok("novo cliente atendido libera a mesa esquecida", m["status"] == "ocupada", m)
n = db("SELECT conta_na_media FROM vw_tempo_mesa_suja WHERE mesa_numero = 40 ORDER BY id DESC LIMIT 1")
ok("mesa esquecida fica fora da média", n == [(0,)], n)

print("\n[7] Raio-X")
prato = {"peso_g": 500, "receita": 44.95, "custo_estimado": 15, "precisao": 80, "origem": "ia",
         "itens": [{"nome": "Picanha", "categoria": "carne", "percentual": 30, "peso_g": 150, "custo": 11.25}]}
pip("600", "entrada", momento=ts(12))
s, t, _ = chamar("POST", "/api/pratos", {**prato, "codigo_comanda": "600"})
ok("prato com comanda grava e pipa balança", s == 201 and db("SELECT min_ate_pesar FROM vw_jornada_cliente WHERE codigo='600'")[0][0] is not None)
ok("prato sem campos = 400", chamar("POST", "/api/pratos", {"peso_g": 10})[0] == 400)
s, _, _ = chamar("POST", "/api/pratos", {**prato, "peso_g": -300})
ok("peso negativo recusado", s == 400, f"status {s} (aceito)")
s, _, _ = chamar("POST", "/api/pratos", {**prato, "peso_g": "abc"})
ok("peso com letras = 400", s == 400, f"status {s}")

print("\n[8] Avaliação (QR Code com desconto/cashback)")
s, t, _ = chamar("POST", "/api/avaliacoes", {"mesa": 12, "codigo_comanda": "100", "nota_comida": 5, "nota_espera": 3,
                                             "gostou": ["Picanha"], "nao_gostou": "Lasanha", "beneficio": "cashback"})
ok("avaliação válida", s == 201)
ok("nota 0 = 400", chamar("POST", "/api/avaliacoes", {"nota_comida": 0})[0] == 400)
ok("nota 'cinco' = 400", chamar("POST", "/api/avaliacoes", {"nota_comida": "cinco"})[0] == 400)
s2, _, _ = chamar("POST", "/api/avaliacoes", {"mesa": 12, "codigo_comanda": "100", "nota_comida": 5, "beneficio": "cashback"})
ok("2ª avaliação da mesma comanda bloqueada (cashback 2x)", s2 == 400, f"status {s2}: aceita de novo")
s, _, _ = chamar("POST", "/api/avaliacoes", {"mesa": 13, "nota_comida": 4, "comentario": "<img src=x onerror=alert(1)>"})
ok("comentário com HTML é aceito como texto", s == 201)
chamar("POST", "/api/avaliacoes", {"mesa": 14, "nota_comida": 4, "comentario": "=HYPERLINK(\"http://x\",\"clique\")"})
csv = chamar("GET", "/api/painel/exportar/avaliacoes.csv", abridor=gerente)[1]
ok("CSV neutraliza fórmula do Excel em comentário", "'=HYPERLINK" in csv, "comentário '=HYPERLINK(...)' sai como fórmula no Excel")
s, _, _ = chamar("POST", "/api/avaliacoes", {"mesa": 12, "nota_comida": 5, "comentario": "x" * 5000})
ok("comentário enorme é cortado", s == 201 and db("SELECT MAX(LENGTH(comentario)) FROM avaliacoes")[0][0] <= 500)

print("\n[9] Quem pode gravar sem login")
info("POST /api/comanda/pipar sem login", pip("999", "entrada")[0])
info("POST /api/avaliacoes sem login", chamar("POST", "/api/avaliacoes", {"nota_comida": 1})[0])
info("POST /api/mesas/1/saiu sem login", chamar("POST", "/api/mesas/1/saiu")[0])
chamar("POST", "/api/mesas/1/limpa")

print("\n[10] Várias estações ao mesmo tempo (60 pips em paralelo)")
res = []
def worker(i):
    res.append(pip(f"P{i}", "entrada")[0])
ths = [threading.Thread(target=worker, args=(i,)) for i in range(60)]
[t.start() for t in ths]; [t.join() for t in ths]
ok("60 pips simultâneos gravados", res.count(201) == 60, {x: res.count(x) for x in set(res)})

print("\n[11] Painel depois dos dados")
for dias in (1, 7, 30):
    s, t, _ = chamar("GET", f"/api/painel/dados?dias={dias}", abridor=gerente)
    ok(f"painel com dados dias={dias}", s == 200)
d = j(t)
info("alertas gerados", [a["titulo"] for a in d["alertas"]])

print("\n=== FALHAS ===")
for a in achados:
    print(" -", a)
print(f"total de falhas: {len(achados)}")
