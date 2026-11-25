-- =====================================================================
-- Painel Gerencial Bovinu'S | banco de dados (SQLite)
--
-- Tabelas simples, uma por "coisa que acontece no salão".
-- Datas sempre no formato 'AAAA-MM-DD HH:MM:SS' (horário local).
-- As VIEWS (vw_*) são o "contrato" de leitura: qualquer sistema da casa
-- (Excel, Power BI, ERP) pode consumir direto delas ou pelo CSV do painel.
-- =====================================================================

PRAGMA foreign_keys = ON;

-- ---------- Cadastros ----------------------------------------------------

-- Mesas dos três salões (mapa da casa: Inferior ~20, Principal ~30, Superior ~40)
CREATE TABLE IF NOT EXISTS mesas (
    numero      INTEGER PRIMARY KEY,
    salao       TEXT NOT NULL CHECK (salao IN ('Inferior', 'Principal', 'Superior')),
    lugares     INTEGER NOT NULL DEFAULT 4
);

-- Itens do buffet e custo por kg (sai do código e vai para o banco: o gerente atualiza)
CREATE TABLE IF NOT EXISTS itens_buffet (
    nome        TEXT PRIMARY KEY,
    categoria   TEXT NOT NULL,              -- carne, acompanhamento, salada, quente, sobremesa, outro
    custo_kg    REAL NOT NULL,              -- R$ por kg
    ativo       INTEGER NOT NULL DEFAULT 1
);

-- ---------- Jornada do cliente (comanda "pipada") ------------------------

-- Uma linha por USO da comanda (o cartão físico volta para a pilha e é reutilizado)
CREATE TABLE IF NOT EXISTS comandas (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo      TEXT NOT NULL,              -- número / código de barras / QR do cartão
    aberta_em   TEXT NOT NULL,              -- 1º pip (normalmente na entrada)
    fechada_em  TEXT,                       -- pip no caixa (pagamento)
    mesa_numero INTEGER REFERENCES mesas(numero)
);
CREATE INDEX IF NOT EXISTS ix_comandas_codigo ON comandas(codigo, fechada_em);
CREATE INDEX IF NOT EXISTS ix_comandas_aberta ON comandas(aberta_em);

-- Cada "pip" da comanda em um ponto do salão
CREATE TABLE IF NOT EXISTS eventos_comanda (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    comanda_id  INTEGER NOT NULL REFERENCES comandas(id),
    tipo        TEXT NOT NULL CHECK (tipo IN ('entrada', 'balanca', 'atendimento_mesa', 'pagamento')),
    momento     TEXT NOT NULL,
    mesa_numero INTEGER REFERENCES mesas(numero),
    ponto       TEXT,                       -- ex.: 'Caixa 1', 'Balança', 'Garçom 3'
    id_cliente  TEXT                        -- id gerado pelo aparelho: reenvio da fila offline não duplica
);
CREATE INDEX IF NOT EXISTS ix_eventos_comanda ON eventos_comanda(comanda_id, tipo);
CREATE UNIQUE INDEX IF NOT EXISTS ux_eventos_id_cliente ON eventos_comanda(id_cliente) WHERE id_cliente IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_eventos_momento ON eventos_comanda(momento);

-- ---------- Raio-X do Prato ----------------------------------------------

CREATE TABLE IF NOT EXISTS pratos (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    comanda_id      INTEGER REFERENCES comandas(id),
    pesado_em       TEXT NOT NULL,
    peso_g          REAL NOT NULL,
    receita         REAL NOT NULL,          -- quanto o cliente paga pelo prato
    custo_estimado  REAL NOT NULL,
    precisao        INTEGER,                -- 0 a 100, devolvida pela IA
    origem          TEXT NOT NULL DEFAULT 'ia',  -- 'ia' (Raio-X) ou 'simulado' (dados de demonstração)
    foto            TEXT                    -- arquivo da foto em dados/fotos/ (pratos do Raio-X)
);
CREATE INDEX IF NOT EXISTS ix_pratos_pesado ON pratos(pesado_em);

CREATE TABLE IF NOT EXISTS itens_prato (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    prato_id    INTEGER NOT NULL REFERENCES pratos(id) ON DELETE CASCADE,
    item        TEXT NOT NULL,
    categoria   TEXT NOT NULL,
    percentual  REAL NOT NULL,              -- % do peso do prato
    peso_g      REAL NOT NULL,
    custo       REAL NOT NULL,              -- R$ (foto do custo no momento da pesagem)
    confianca   INTEGER
);
CREATE INDEX IF NOT EXISTS ix_itens_prato ON itens_prato(prato_id);

-- ---------- Controle das mesas -------------------------------------------

-- Um ciclo "cliente saiu -> mesa limpa". limpa_em vazio = mesa ainda suja.
CREATE TABLE IF NOT EXISTS limpezas_mesa (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    mesa_numero INTEGER NOT NULL REFERENCES mesas(numero),
    saiu_em     TEXT NOT NULL,
    limpa_em    TEXT,
    origem      TEXT NOT NULL DEFAULT 'garcom',  -- quem marcou SUJA: 'garcom' (toque) ou 'caixa' (última comanda da mesa pagou)
    limpa_origem TEXT                        -- quem marcou LIMPA: 'garcom' (toque) ou 'novo_cliente' (garçom atendeu
                                            -- a mesa sem ter tocado "limpa"; fica fora das médias)
);
CREATE INDEX IF NOT EXISTS ix_limpezas_aberta ON limpezas_mesa(mesa_numero, limpa_em);
CREATE INDEX IF NOT EXISTS ix_limpezas_saiu ON limpezas_mesa(saiu_em);

-- ---------- Avaliação do cliente (QR Code na mesa) -----------------------

CREATE TABLE IF NOT EXISTS avaliacoes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    criada_em       TEXT NOT NULL,
    mesa_numero     INTEGER REFERENCES mesas(numero),
    comanda_id      INTEGER REFERENCES comandas(id),   -- liga a nota ao tempo REAL medido
    nota_comida     INTEGER CHECK (nota_comida BETWEEN 1 AND 5),
    nota_espera     INTEGER CHECK (nota_espera BETWEEN 1 AND 5),
    comentario      TEXT,
    tema            TEXT,                   -- comida, espera, limpeza, atendimento, outro (IA ou palavras-chave)
    beneficio       TEXT,                   -- 'desconto' / 'cashback' concedido por responder
    nota_limpeza    INTEGER CHECK (nota_limpeza BETWEEN 1 AND 5),
    motivo          TEXT,                   -- "O que não estava bom nesses itens?" (ex.: Frio, Salgado, Outro)
    origem          TEXT,                   -- 'planilha' (Google Forms), 'api' ou 'simulado'
    chave_origem    TEXT                    -- impressão digital da linha da planilha: não importa 2 vezes
);
CREATE INDEX IF NOT EXISTS ix_avaliacoes_criada ON avaliacoes(criada_em);
CREATE UNIQUE INDEX IF NOT EXISTS ux_avaliacoes_chave ON avaliacoes(chave_origem) WHERE chave_origem IS NOT NULL;

-- Itens que o cliente marcou como "mais gostei" / "não estava bom"
CREATE TABLE IF NOT EXISTS avaliacao_itens (
    avaliacao_id    INTEGER NOT NULL REFERENCES avaliacoes(id) ON DELETE CASCADE,
    item            TEXT NOT NULL,
    opiniao         TEXT NOT NULL CHECK (opiniao IN ('gostou', 'nao_gostou'))
);
CREATE INDEX IF NOT EXISTS ix_avaliacao_itens ON avaliacao_itens(avaliacao_id);

-- Configurações do painel (ex.: marca 'dados_simulados' enquanto não há dados reais)
CREATE TABLE IF NOT EXISTS meta (
    chave   TEXT PRIMARY KEY,
    valor   TEXT
);

-- =====================================================================
-- VIEWS: o que o restaurante consome
-- =====================================================================

-- Jornada de cada cliente: quanto tempo levou da entrada até pesar, até ser
-- atendido na mesa e até pagar.
DROP VIEW IF EXISTS vw_jornada_cliente;
CREATE VIEW vw_jornada_cliente AS
WITH e AS (
    SELECT comanda_id,
           MIN(CASE WHEN tipo = 'entrada'          THEN momento END) AS entrada,
           MIN(CASE WHEN tipo = 'balanca'          THEN momento END) AS primeira_balanca,
           MIN(CASE WHEN tipo = 'atendimento_mesa' THEN momento END) AS atendido_mesa,
           MAX(CASE WHEN tipo = 'pagamento'        THEN momento END) AS pagamento,
           SUM(tipo = 'balanca')                                     AS qtd_pesagens
    FROM eventos_comanda GROUP BY comanda_id
)
SELECT c.id AS comanda_id, c.codigo, c.mesa_numero, m.salao,
       e.entrada, e.primeira_balanca, e.atendido_mesa, e.pagamento, e.qtd_pesagens,
       CAST(strftime('%H', e.entrada) AS INTEGER)                            AS hora_entrada,
       ROUND((julianday(e.primeira_balanca) - julianday(e.entrada)) * 1440, 1) AS min_ate_pesar,
       ROUND((julianday(e.atendido_mesa) - julianday(e.primeira_balanca)) * 1440, 1) AS min_ate_atendimento_mesa,
       ROUND((julianday(e.pagamento) - julianday(e.entrada)) * 1440, 1)        AS min_permanencia
FROM comandas c
JOIN e ON e.comanda_id = c.id
LEFT JOIN mesas m ON m.numero = c.mesa_numero;

-- Cada ciclo de limpeza com o tempo de mesa suja
DROP VIEW IF EXISTS vw_tempo_mesa_suja;
CREATE VIEW vw_tempo_mesa_suja AS
SELECT l.id, l.mesa_numero, m.salao, l.saiu_em, l.limpa_em, l.origem, l.limpa_origem,
       CAST(strftime('%H', l.saiu_em) AS INTEGER)                       AS hora,
       ROUND((julianday(l.limpa_em) - julianday(l.saiu_em)) * 1440, 1) AS min_suja,
       -- entra na média só se o garçom tocou "limpa" e o tempo é plausível (até 90 min)
       CASE WHEN l.limpa_em IS NOT NULL AND COALESCE(l.limpa_origem, 'garcom') = 'garcom'
                 AND (julianday(l.limpa_em) - julianday(l.saiu_em)) * 1440 <= 90 THEN 1 ELSE 0 END AS conta_na_media
FROM limpezas_mesa l
LEFT JOIN mesas m ON m.numero = l.mesa_numero;

-- Pratos com margem
DROP VIEW IF EXISTS vw_pratos;
CREATE VIEW vw_pratos AS
SELECT p.*, CAST(strftime('%H', p.pesado_em) AS INTEGER) AS hora,
       ROUND(p.receita - p.custo_estimado, 2)                         AS lucro_bruto,
       ROUND((p.receita - p.custo_estimado) / NULLIF(p.receita, 0), 4) AS margem,
       ROUND(p.custo_estimado / NULLIF(p.peso_g, 0) * 1000, 2)        AS custo_por_kg
FROM pratos p;

-- Mix: quanto cada item pesa e quanto custa no total
DROP VIEW IF EXISTS vw_mix_itens;
CREATE VIEW vw_mix_itens AS
SELECT ip.item, ip.categoria, p.pesado_em, ip.peso_g, ip.custo, ip.percentual, ip.prato_id
FROM itens_prato ip JOIN pratos p ON p.id = ip.prato_id;

-- Opinião por item (elogios x críticas)
DROP VIEW IF EXISTS vw_opiniao_itens;
CREATE VIEW vw_opiniao_itens AS
SELECT a.criada_em, a.mesa_numero, a.origem, ai.item, ai.opiniao, a.motivo
FROM avaliacao_itens ai JOIN avaliacoes a ON a.id = ai.avaliacao_id;
