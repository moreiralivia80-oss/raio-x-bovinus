"""Testes do painel. Rodar na pasta do projeto:  python -m unittest discover testes"""
import os
import tempfile
import unittest
from datetime import datetime, timedelta

_PASTA = tempfile.mkdtemp()
os.environ["BOVINUS_DB"] = os.path.join(_PASTA, "teste.db")
os.environ["PAINEL_SENHA"] = "senha-teste"
os.environ["PLANILHA_AVALIACOES"] = "desligado"  # testes não acessam a internet

from painel import banco, eventos, metricas, planilha, simulador  # noqa: E402

T0 = datetime(2026, 11, 20, 12, 0, 0)


def t(minutos):
    return T0 + timedelta(minutes=minutos)


class BancoLimpo(unittest.TestCase):
    def setUp(self):
        self.con = banco.conectar(os.path.join(_PASTA, f"{self.id()}.db"))
        banco.criar_tabelas(self.con)

    def tearDown(self):
        self.con.close()


class TestJornadaComanda(BancoLimpo):
    def test_tempos_da_jornada(self):
        eventos.pipar(self.con, "77", "entrada", t(0))
        r = eventos.pipar(self.con, "77", "balanca", t(8.5))
        self.assertEqual(r["minutos_desde_entrada"], 8.5)
        eventos.pipar(self.con, "77", "atendimento_mesa", t(11), mesa=32)
        eventos.pipar(self.con, "77", "pagamento", t(45))
        j = self.con.execute("SELECT * FROM vw_jornada_cliente").fetchone()
        self.assertEqual((j["min_ate_pesar"], j["min_ate_atendimento_mesa"], j["min_permanencia"]), (8.5, 2.5, 45.0))
        self.assertEqual(j["mesa_numero"], 32)

    def test_mesa_fica_suja_so_quando_a_ultima_comanda_paga(self):
        for codigo in ("1", "2"):
            eventos.pipar(self.con, codigo, "entrada", t(0))
            eventos.pipar(self.con, codigo, "atendimento_mesa", t(10), mesa=5)
        r1 = eventos.pipar(self.con, "1", "pagamento", t(40))
        self.assertNotIn("mesa_suja", r1)
        r2 = eventos.pipar(self.con, "2", "pagamento", t(42))
        self.assertEqual(r2["mesa_suja"]["mesa"], 5)
        limpa = eventos.mesa_limpa(self.con, 5, t(49))
        self.assertEqual(limpa["minutos_suja"], 7.0)

    def test_comanda_reutilizada_abre_novo_uso(self):
        eventos.pipar(self.con, "9", "entrada", t(0))
        eventos.pipar(self.con, "9", "pagamento", t(30))
        r = eventos.pipar(self.con, "9", "entrada", t(60))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM comandas").fetchone()[0], 2)
        self.assertEqual(r["comanda_id"], 2)

    def test_pip_sem_entrada_avisa(self):
        r = eventos.pipar(self.con, "5", "balanca", t(0))
        self.assertIn("aviso", r)

    def test_mesa_inexistente(self):
        with self.assertRaises(ValueError):
            eventos.pipar(self.con, "5", "atendimento_mesa", t(0), mesa=999)


class TestMesas(BancoLimpo):
    def test_toque_duplo_nao_duplica(self):
        eventos.mesa_saiu(self.con, 10, t(0))
        r = eventos.mesa_saiu(self.con, 10, t(1))
        self.assertTrue(r["ja_estava_suja"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM limpezas_mesa").fetchone()[0], 1)

    def test_limpar_mesa_ja_limpa(self):
        self.assertFalse(eventos.mesa_limpa(self.con, 10, t(0))["estava_suja"])


class TestRaioXEAvaliacao(BancoLimpo):
    RESULTADO = {"peso_g": 500, "receita": 44.95, "custo_estimado": 15.0, "precisao": 82, "origem": "ia",
                 "itens": [{"nome": "Picanha", "categoria": "carne", "percentual": 20, "peso_g": 100, "custo": 7.5, "confianca": 90},
                           {"nome": "Arroz", "categoria": "acompanhamento", "percentual": 80, "peso_g": 400, "custo": 7.5, "confianca": 95}]}

    def test_prato_com_comanda_registra_balanca(self):
        eventos.pipar(self.con, "12", "entrada", t(0))
        eventos.registrar_prato(self.con, self.RESULTADO, "12", t(6))
        j = self.con.execute("SELECT min_ate_pesar FROM vw_jornada_cliente").fetchone()
        self.assertEqual(j[0], 6.0)
        p = self.con.execute("SELECT margem FROM vw_pratos").fetchone()
        self.assertAlmostEqual(p[0], (44.95 - 15) / 44.95, places=3)

    def test_avaliacao_com_itens_e_tema(self):
        eventos.pipar(self.con, "3", "entrada", t(0))
        aid = eventos.registrar_avaliacao(self.con, {
            "mesa": 3, "codigo_comanda": "3", "nota_comida": 5, "nota_espera": 2,
            "gostou": "Picanha, Farofa", "nao_gostou": ["Lasanha"], "comentario": "Fila da churrasqueira demorada",
            "criada_em": t(40)})
        a = self.con.execute("SELECT * FROM avaliacoes WHERE id = ?", (aid,)).fetchone()
        self.assertEqual((a["tema"], a["comanda_id"]), ("espera", 1))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM avaliacao_itens").fetchone()[0], 3)

    def test_nota_invalida(self):
        with self.assertRaises(ValueError):
            eventos.registrar_avaliacao(self.con, {"nota_comida": 7})

    def test_classificar_tema(self):
        self.assertEqual(eventos.classificar_tema("A mesa estava suja"), "limpeza")
        self.assertEqual(eventos.classificar_tema("Picanha no ponto"), "comida")
        self.assertIsNone(eventos.classificar_tema(""))


CSV_FORMULARIO = (
    "Carimbo de data/hora,1. Como você avalia a comida? ,2. Como você avalia o tempo de espera?  ,"
    "3. Como você avalia a limpeza da mesa e do salão?  ,4. Quais itens você mais gostou hoje?  ,"
    "5. Algum item não estava bom?  ,6. O que não estava bom nesses itens?  ,7. Quer nos contar mais alguma coisa?  \r\n"
    "25/11/2026 19:43:08,5 - Excelente,5 - Muito Rápido,5 - Impecável,Churrasco: Picanha,Estava tudo bom,Outro,\r\n"
    "25/11/2026 20:09:24,4 - Bom,2 - Demorado,2 - Ruim,\"Churrasco: Picanha, Quentes: Feijoada\",Arroz,Aparência ruim,"
    "Fila da churrasqueira muito grande\r\n"
    "25/11/2026 20:15:00,9 - ???,4 - Rápido,,,,,\r\n"
)


class TestPlanilhaDoFormulario(BancoLimpo):
    def test_perguntas_reconhecidas(self):
        _, _, _, campos = planilha.importar_texto(self.con, CSV_FORMULARIO)
        self.assertEqual(sorted(campos.values()), sorted([
            "criada_em", "nota_comida", "nota_espera", "nota_limpeza", "gostou", "nao_gostou", "motivo", "comentario"]))

    def test_importa_sem_duplicar(self):
        novas, repetidas, erros, _ = planilha.importar_texto(self.con, CSV_FORMULARIO)
        self.assertEqual((novas, repetidas, len(erros)), (2, 0, 1))  # 3ª linha tem nota 9
        novas, repetidas, _, _ = planilha.importar_texto(self.con, CSV_FORMULARIO)
        self.assertEqual((novas, repetidas), (0, 2))
        a = self.con.execute("SELECT * FROM avaliacoes ORDER BY id").fetchall()
        self.assertEqual((a[0]["nota_comida"], a[0]["nota_espera"], a[0]["nota_limpeza"]), (5, 5, 5))
        self.assertIsNone(a[0]["motivo"])  # "Estava tudo bom": motivo não vale
        self.assertEqual((a[1]["nota_limpeza"], a[1]["motivo"], a[1]["tema"], a[1]["origem"]),
                         (2, "Aparência ruim", "espera", "planilha"))
        itens = self.con.execute("SELECT item, opiniao FROM avaliacao_itens WHERE avaliacao_id = ?", (a[1]["id"],)).fetchall()
        self.assertEqual(sorted(map(tuple, itens)), [("Arroz", "nao_gostou"), ("Feijoada", "gostou"), ("Picanha", "gostou")])

    def test_link_de_edicao_vira_csv(self):
        self.assertEqual(planilha.url_csv(planilha.PLANILHA_PADRAO),
                         "https://docs.google.com/spreadsheets/d/1XTmWoDvZiKXfRDBuAWlE5j5tTUdJ3kxGXqxXPjlmr0s/"
                         "export?format=csv&gid=1675468231")

    def test_filtro_so_reais(self):
        simulador.gerar(self.con, dias=2, agora=datetime(2026, 11, 25, 21, 0))
        planilha.importar_texto(self.con, CSV_FORMULARIO)
        agora = datetime(2026, 11, 25, 21, 0)
        todas = metricas.montar_painel(self.con, 1, agora)["avaliacoes"]
        reais = metricas.montar_painel(self.con, 1, agora, so_reais=True)["avaliacoes"]
        self.assertEqual(reais["respostas"], 2)
        self.assertGreater(todas["respostas"], 2)
        self.assertEqual(reais["media"]["limpeza"], 3.5)


class TestLeituraRepetidaEOffline(BancoLimpo):
    def test_leitor_que_le_duas_vezes(self):
        eventos.pipar(self.con, "50", "entrada", t(0))
        r = eventos.pipar(self.con, "50", "entrada", t(0.3))
        self.assertTrue(r["repetida"])
        eventos.pipar(self.con, "50", "pagamento", t(40))
        eventos.pipar(self.con, "50", "pagamento", t(40.5))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM comandas").fetchone()[0], 1)

    def test_segundo_prato_conta(self):
        eventos.pipar(self.con, "51", "entrada", t(0))
        eventos.pipar(self.con, "51", "balanca", t(8))
        eventos.pipar(self.con, "51", "balanca", t(25))
        self.assertEqual(self.con.execute("SELECT qtd_pesagens FROM vw_jornada_cliente").fetchone()[0], 2)

    def test_reenvio_da_fila_offline_nao_duplica(self):
        eventos.pipar(self.con, "52", "entrada", t(0), id_cliente="abc")
        r = eventos.pipar(self.con, "52", "entrada", t(5), id_cliente="abc")  # mesmo toque reenviado depois
        self.assertTrue(r["repetida"])
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM eventos_comanda").fetchone()[0], 1)

    def test_garcom_sem_mesa(self):
        with self.assertRaises(ValueError):
            eventos.pipar(self.con, "53", "atendimento_mesa", t(0))


class TestMesasConectadas(BancoLimpo):
    def test_mesa_inexistente(self):
        for funcao in (eventos.mesa_saiu, eventos.mesa_limpa, eventos.mesa_desfazer):
            with self.assertRaises(ValueError):
                funcao(self.con, 999, t(0))

    def test_cliente_novo_libera_mesa_esquecida(self):
        eventos.mesa_saiu(self.con, 8, t(0))
        eventos.pipar(self.con, "60", "entrada", t(300))
        eventos.pipar(self.con, "60", "atendimento_mesa", t(310), mesa=8)
        l = self.con.execute("SELECT * FROM vw_tempo_mesa_suja").fetchone()
        self.assertEqual((l["limpa_origem"], l["conta_na_media"]), ("novo_cliente", 0))

    def test_tempo_absurdo_fica_fora_da_media(self):
        eventos.mesa_saiu(self.con, 9, t(0))
        eventos.mesa_limpa(self.con, 9, t(600))
        eventos.mesa_saiu(self.con, 10, t(0))
        eventos.mesa_limpa(self.con, 10, t(6))
        r = metricas._resumo(self.con, "2026-11-20 00:00:00", "2026-11-21 00:00:00")
        self.assertEqual((r["min_mesa_suja"], r["limpezas_fora_da_media"]), (6.0, 1))

    def test_desfazer(self):
        eventos.mesa_saiu(self.con, 11, t(0))
        self.assertEqual(eventos.mesa_desfazer(self.con, 11, t(1))["status"], "livre")
        eventos.mesa_saiu(self.con, 11, t(2))
        eventos.mesa_limpa(self.con, 11, t(7))
        self.assertEqual(eventos.mesa_desfazer(self.con, 11, t(8))["status"], "suja")
        with self.assertRaises(ValueError):  # passou do prazo de 2 min
            eventos.mesa_desfazer(self.con, 11, t(30))

    def test_limpa_guardada_offline_nao_fica_antes_do_saiu(self):
        eventos.mesa_saiu(self.con, 12, t(10))
        self.assertEqual(eventos.mesa_limpa(self.con, 12, t(5))["minutos_suja"], 0.0)


class TestMigracao(unittest.TestCase):
    def test_banco_antigo_ganha_colunas(self):
        import sqlite3
        caminho = os.path.join(_PASTA, "antigo.db")
        con = sqlite3.connect(caminho)
        con.executescript("""CREATE TABLE avaliacoes (id INTEGER PRIMARY KEY, criada_em TEXT NOT NULL, mesa_numero INTEGER,
            comanda_id INTEGER, nota_comida INTEGER, nota_espera INTEGER, comentario TEXT, tema TEXT, beneficio TEXT);
            INSERT INTO avaliacoes (criada_em, nota_comida) VALUES ('2026-11-20 12:00:00', 4);""")
        con.commit()
        con.close()
        con = banco.conectar(caminho)
        banco.criar_tabelas(con)
        colunas = {r[1] for r in con.execute("PRAGMA table_info(avaliacoes)")}
        self.assertTrue({"nota_limpeza", "motivo", "origem", "chave_origem"} <= colunas)
        self.assertEqual(con.execute("SELECT nota_comida FROM avaliacoes").fetchone()[0], 4)
        con.close()


class TestPainelComSimulador(BancoLimpo):
    def test_painel_completo(self):
        agora = datetime(2026, 11, 25, 15, 0)
        simulador.gerar(self.con, dias=10, agora=agora)
        d = metricas.montar_painel(self.con, 7, agora)
        self.assertTrue(d["dados_simulados"])
        self.assertGreater(d["resumo"]["clientes"], 1000)
        self.assertTrue(0.5 < d["resumo"]["margem"] < 0.9)
        self.assertEqual(len(d["mesas_agora"]), 90)
        self.assertAlmostEqual(sum(i["pct_custo"] for i in d["mix_itens"]), 1, places=2)
        self.assertTrue(d["alertas"])
        # nada no futuro
        futuro = self.con.execute("SELECT COUNT(*) FROM eventos_comanda WHERE momento > ?",
                                  (agora.strftime(banco.FORMATO),)).fetchone()[0]
        self.assertEqual(futuro, 0)


class TestRotas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from flask import Flask
        from painel import bp
        app = Flask(__name__)
        app.secret_key = "teste"
        app.register_blueprint(bp)
        cls.app = app

    def setUp(self):
        self.c = self.app.test_client()

    def test_painel_pede_login(self):
        self.assertEqual(self.c.get("/painel").status_code, 302)
        self.assertEqual(self.c.get("/api/painel/dados").status_code, 401)

    def test_login_errado_e_certo(self):
        self.assertEqual(self.c.post("/painel/login", data={"usuario": "gerente", "senha": "x"}).status_code, 401)
        r = self.c.post("/painel/login", data={"usuario": "gerente", "senha": "senha-teste"})
        self.assertEqual(r.status_code, 302)
        self.assertEqual(self.c.get("/api/painel/dados?dias=7").status_code, 200)
        csv = self.c.get("/api/painel/exportar/vw_jornada_cliente.csv")
        self.assertEqual(csv.status_code, 200)
        self.assertIn("min_ate_pesar", csv.get_data(as_text=True))
        self.assertEqual(self.c.get("/api/painel/exportar/sqlite_master.csv").status_code, 404)

    def test_redirecionamento_externo_bloqueado(self):
        r = self.c.post("/painel/login?proximo=//site-malicioso.com",
                        data={"usuario": "gerente", "senha": "senha-teste"})
        self.assertTrue(r.headers["Location"].endswith("/painel"))

    def test_api_pip_e_mesas(self):
        r = self.c.post("/api/comanda/pipar", json={"codigo": "500", "tipo": "entrada"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.c.post("/api/comanda/pipar", json={"codigo": "500", "tipo": "xx"}).status_code, 400)
        self.assertEqual(self.c.post("/api/mesas/12/saiu").status_code, 200)
        mesas = self.c.get("/api/mesas").get_json()
        self.assertEqual(next(m for m in mesas if m["numero"] == 12)["status"], "suja")
        self.assertTrue(self.c.post("/api/mesas/12/limpa").get_json()["estava_suja"])
        self.assertEqual(self.c.post("/api/mesas/999/saiu").status_code, 400)
        self.assertEqual(self.c.get("/garcom").status_code, 200)
        self.c.post("/api/mesas/13/saiu")
        self.assertEqual(self.c.post("/api/mesas/13/desfazer").get_json()["status"], "livre")

    def test_csv_nao_vira_formula_no_excel(self):
        self.c.post("/api/avaliacoes", json={"nota_comida": 3, "comentario": "=HYPERLINK(\"http://x\")"})
        self.c.post("/painel/login", data={"usuario": "gerente", "senha": "senha-teste"})
        csv = self.c.get("/api/painel/exportar/avaliacoes.csv").get_data(as_text=True)
        self.assertIn("'=HYPERLINK", csv)

    def test_sincronizar_com_planilha_desligada(self):
        self.c.post("/painel/login", data={"usuario": "gerente", "senha": "senha-teste"})
        r = self.c.post("/api/painel/sincronizar").get_json()
        self.assertIn("desligada", r["mensagem"])


if __name__ == "__main__":
    unittest.main()
