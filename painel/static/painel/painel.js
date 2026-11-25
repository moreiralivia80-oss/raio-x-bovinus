// Painel do gerente: busca /api/painel/dados, desenha tudo e se atualiza sozinho.

const ATUALIZAR_A_CADA_MS = 60_000;
const COR = { azul: "#2a78d6", laranja: "#eb6834", aqua: "#1baf7a", neg: "#e34948" };

const PARAMS = new URLSearchParams(location.search);
let dias = Number(PARAMS.get("dias")) || 7;
let soReais = PARAMS.get("reais") === "1"; // Dor 4: só respostas da planilha (ignora as simuladas)
let ultimo = null;

// ---------- formatos pt-BR ----------
const num = (v, c = 1) => (v == null ? "–" : v.toLocaleString("pt-BR", { minimumFractionDigits: c, maximumFractionDigits: c }));
const reais = (v) => (v == null ? "–" : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" }));
const pct = (v, c = 0) => (v == null ? "–" : num(v * 100, c) + "%");
const min = (v) => (v == null ? "–" : num(v) + " min");
const inteiro = (v) => (v == null ? "–" : Math.round(v).toLocaleString("pt-BR"));
const sinal = (v, f) => (v > 0 ? "+" : v < 0 ? "−" : "±") + f(Math.abs(v));

// ---------- números do topo ----------
const KPIS = [
  { chave: "custo_medio", rotulo: "Custo médio do prato", fmt: reais, melhor: "menor", extra: (r) => `cliente paga ${reais(r.receita_media)} em média` },
  { chave: "custo_kg", rotulo: "Custo da comida por kg", fmt: reais, melhor: "menor", extra: (r) => `prato médio de ${inteiro(r.peso_medio_g)} g` },
  { chave: "clientes", rotulo: "Clientes (comandas)", fmt: inteiro, melhor: null, extra: (r) => `${inteiro(r.pratos)} pratos pesados` },
  { chave: "min_ate_pesar", rotulo: "Da entrada até a balança", fmt: min, melhor: "menor", extra: (r) => `1 em cada 10: ${min(r.min_ate_pesar_p90)}` },
  { chave: "min_atendimento_mesa", rotulo: "Garçom chega à mesa", fmt: min, melhor: "menor", extra: () => "depois de pesar o prato" },
  { chave: "min_mesa_suja", rotulo: "Mesa suja até limpar", fmt: min, melhor: "menor", extra: (r) => `1 em cada 10: ${min(r.min_mesa_suja_p90)}` },
  { chave: "nota_comida", rotulo: "Nota da comida", fmt: (v) => (v == null ? "–" : num(v) + " / 5"), melhor: "maior", extra: (r) => `${inteiro(r.avaliacoes)} avaliações` },
  { chave: "nota_espera", rotulo: "Nota do tempo de espera", fmt: (v) => (v == null ? "–" : num(v) + " / 5"), melhor: "maior", extra: (r) => `${pct(r.taxa_resposta)} das comandas responderam` },
];

function textoDelta(k, atual, anterior) {
  const a = atual[k.chave], b = anterior[k.chave];
  if (a == null || b == null || k.melhor === null) return { texto: "", classe: "" };
  const dif = a - b;
  const fmtDif = k.chave.startsWith("min") ? (v) => num(v) + " min"
    : k.chave.startsWith("nota") ? (v) => num(v, 2)
    : k.fmt === reais ? reais : (v) => num(v);
  const ref = dias === 1 ? "vs ontem" : dias === 7 ? "vs semana anterior" : `vs ${dias} dias antes`;
  const neutro = Math.abs(dif) < (k.chave.startsWith("nota") ? 0.02 : 0.05);
  const bom = (dif < 0) === (k.melhor === "menor");
  return { texto: `${sinal(dif, fmtDif)} ${ref}`, classe: neutro ? "" : bom ? "delta--bom" : "delta--ruim" };
}

function desenharNumeros(d) {
  const r = d.resumo, a = d.resumo_anterior;
  const difMargem = r.margem != null && a.margem != null ? (r.margem - a.margem) * 100 : null;
  const ref = dias === 1 ? "vs ontem" : dias === 7 ? "vs semana anterior" : `vs ${dias} dias antes`;
  let html = `<div class="heroi">
      <span class="rotulo">Margem estimada do buffet</span>
      <span class="valor">${pct(r.margem, 1)}</span>
      <span class="delta ${difMargem == null || Math.abs(difMargem) < 0.1 ? "" : difMargem > 0 ? "delta--bom" : "delta--ruim"}">
        ${difMargem == null ? "" : sinal(difMargem, (v) => num(v) + " p.p.") + " " + ref}</span>
      <p class="nota">(preço do kg − custo dos itens identificados pelo Raio-X) ÷ preço do kg</p>
    </div>`;
  for (const k of KPIS) {
    const dlt = textoDelta(k, r, a);
    html += `<div class="kpi"><div class="rotulo">${k.rotulo}</div><div class="valor">${k.fmt(r[k.chave])}</div>
      <div class="extra">${k.extra(r)}</div><div class="delta ${dlt.classe}">${dlt.texto}</div></div>`;
  }
  document.getElementById("numeros").innerHTML = html;
}

// ---------- alertas ----------
function desenharAlertas(lista) {
  const icone = { critico: "!", atencao: "!", info: "i" };
  const nome = { critico: "Crítico", atencao: "Atenção", info: "Informação" };
  document.getElementById("alertas").innerHTML = lista.map((a) => `
    <li class="alerta alerta--${a.nivel}">
      <span class="alerta__icone" aria-hidden="true">${icone[a.nivel]}</span>
      <div><span class="alerta__nivel">${nome[a.nivel]}</span><strong>${G.esc(a.titulo)}</strong><p>${G.esc(a.texto)}</p></div>
    </li>`).join("");
}

// ---------- mapa de mesas ----------
function desenharMapa(mesas) {
  const saloes = ["Inferior", "Principal", "Superior"];
  const nomes = { Inferior: "Salão Inferior (pista)", Principal: "Salão Principal", Superior: "Salão Superior" };
  document.getElementById("mapa").innerHTML = saloes.map((s) => {
    const doSalao = mesas.filter((m) => m.salao === s);
    const sujas = doSalao.filter((m) => m.status === "suja").length;
    const cel = doSalao.map((m) => {
      let classe = "", texto = `Mesa ${m.numero}, livre`, extra = "";
      if (m.status === "ocupada") { classe = "mesa--ocupada"; texto = `Mesa ${m.numero}, ocupada`; }
      if (m.status === "suja") {
        classe = m.minutos < 5 ? "mesa--suja-1" : m.minutos < 10 ? "mesa--suja-2" : "mesa--suja-3";
        texto = `Mesa ${m.numero}, suja há ${m.minutos} min`;
        extra = `<small>${m.minutos}m</small>`;
      }
      return `<div class="mesa ${classe}" title="${texto}" aria-label="${texto}">${m.numero}${extra}</div>`;
    }).join("");
    return `<div class="salao"><h4>${nomes[s]} <span>${sujas} suja(s)</span></h4><div class="mesas">${cel}</div></div>`;
  }).join("");
}

// ---------- tabela de itens ----------
function desenharItens(mix) {
  const linhas = [...mix].sort((a, b) => b.pct_pratos - a.pct_pratos);
  document.getElementById("t-itens").innerHTML = `
    <thead><tr><th>Item</th><th class="num">Presença</th><th class="num">% do peso</th><th class="num">% do custo</th><th class="num">Custo total</th></tr></thead>
    <tbody>${linhas.map((i) => `<tr>
      <td>${G.esc(i.item)}${i.pct_pratos < 0.1 && i.categoria !== "sobremesa" ? '<span class="etiqueta">pouca saída</span>' : ""}${i.pct_custo - i.pct_peso > 0.05 ? '<span class="etiqueta etiqueta--azul">pesa no custo</span>' : ""}</td>
      <td class="num">${pct(i.pct_pratos)}</td><td class="num">${pct(i.pct_peso, 1)}</td>
      <td class="num">${pct(i.pct_custo, 1)}</td><td class="num">${reais(i.custo_total)}</td></tr>`).join("")}</tbody>`;
}

function desenharRaioX(rx) {
  if (!rx) return;
  document.getElementById("raiox-numeros").innerHTML = [
    ["Pratos registrados", inteiro(rx.pratos), `${inteiro(rx.pela_ia)} pela IA na balança · ${inteiro(rx.com_foto)} com foto`],
    ["Peso médio do prato", rx.peso_medio_g == null ? "–" : inteiro(rx.peso_medio_g) + " g", ""],
    ["Custo médio do prato", reais(rx.custo_medio), ""],
    ["Precisão média da IA", rx.precisao_media == null ? "–" : rx.precisao_media + "%", "quanto a IA teve certeza nas fotos"],
  ].map(([rot, val, extra]) => `<div class="kpi"><div class="rotulo">${rot}</div><div class="valor">${val}</div><div class="extra">${extra}</div></div>`).join("");

  G.barrasH(document.getElementById("g-consumidos"), rx.mais_consumidos.slice(0, 10), {
    titulo: "Em quantos pratos cada item apareceu", rotulo: "item", nomeRotulo: "Item", fmt: inteiro, passoMin: 1,
    series: [{ chave: "pratos", nome: "Pratos com o item", cor: COR.azul }],
    extraDica: (l) => `<div class="linha"><span>Presença</span><strong>${pct(l.pct_pratos)}</strong></div>` +
      `<div class="linha"><span>Servido</span><strong>${num(l.peso_kg)} kg</strong></div>`,
    vazio: "Nenhum prato registrado no período. Analise um prato no Raio-X.",
  });

  document.getElementById("t-consumidos").innerHTML = rx.mais_consumidos.length ? `
    <thead><tr><th>#</th><th>Produto</th><th class="num">Pratos</th><th class="num">Presença</th><th class="num">Servido</th><th class="num">Custo</th><th class="num">Certeza</th></tr></thead>
    <tbody>${rx.mais_consumidos.map((p, i) => `<tr><td>${i + 1}</td><td>${G.esc(p.item)}</td>
      <td class="num">${inteiro(p.pratos)}</td><td class="num">${pct(p.pct_pratos)}</td>
      <td class="num">${num(p.peso_kg)} kg</td><td class="num">${reais(p.custo_total)}</td>
      <td class="num">${p.confianca_media == null ? "–" : p.confianca_media + "%"}</td></tr>`).join("")}</tbody>`
    : `<tbody><tr><td class="vazio">Nenhum prato registrado no período.</td></tr></tbody>`;

  const lista = document.getElementById("raiox-ultimos");
  lista.innerHTML = rx.ultimos.length ? rx.ultimos.map((p) => `<li class="raiox-prato">
      ${p.tem_foto ? `<img src="/painel/foto/${p.id}" alt="Foto do prato ${p.id}" loading="lazy">` : `<div class="raiox-sem-foto">sem foto</div>`}
      <div class="raiox-prato__info">
        <strong>${p.pesado_em.slice(8, 10)}/${p.pesado_em.slice(5, 7)} às ${p.pesado_em.slice(11, 16)}</strong>
        <span>${inteiro(p.peso_g)} g · custo ${reais(p.custo)} · cliente paga ${reais(p.receita)}</span>
        <span>${p.itens.slice(0, 5).map((i) => `${G.esc(i.item)} ${num(i.percentual, 0)}%`).join(", ")}${p.itens.length > 5 ? "…" : ""}</span>
        <span class="raiox-prato__ia">${p.origem === "ia" ? "IA" : "simulado"}${p.precisao == null ? "" : ` · precisão ${p.precisao}%`}</span>
      </div></li>`).join("")
    : `<li class="vazio">Nenhum prato registrado no período.</li>`;
}

function desenharComentarios(lista) {
  const el = document.getElementById("comentarios");
  if (!lista.length) { el.innerHTML = '<li class="vazio">Nenhum comentário no período.</li>'; return; }
  el.innerHTML = lista.map((c) => `<li><q>${G.esc(c.comentario)}</q>
    <span class="meta">${G.esc(c.tema || "")} · mesa ${c.mesa_numero ?? "–"} · comida ${c.nota_comida ?? "–"}/5 · espera ${c.nota_espera ?? "–"}/5 · ${c.criada_em.slice(8, 10)}/${c.criada_em.slice(5, 7)} ${c.criada_em.slice(11, 16)}</span></li>`).join("");
}

// ---------- fonte da pesquisa e nota da limpeza ----------
function desenharFonte(d) {
  const av = d.avaliacoes, pl = d.planilha || {};
  const daPlanilha = av.por_origem.planilha || 0, simuladas = av.por_origem.simulado || 0;
  let texto = `<strong>${inteiro(daPlanilha)}</strong> resposta(s) da planilha no período`;
  if (simuladas) texto += ` · ${inteiro(simuladas)} simulada(s)`;
  if (!pl.configurada) texto += " · sincronização com a planilha desligada";
  else if (pl.ultima) {
    const hora = pl.ultima.slice(11, 16);
    texto += pl.ok === false
      ? ` · <span class="erro-sync">falha às ${hora}: ${G.esc(pl.mensagem)}</span>`
      : ` · sincronizado às ${hora} (${G.esc(pl.mensagem.toLowerCase())})`;
  } else texto += " · sincronizando…";
  document.getElementById("fonte-texto").innerHTML = texto;

  const nl = document.getElementById("nota-limpeza");
  const m = av.media.limpeza;
  nl.hidden = m == null;
  if (m != null) nl.innerHTML = `Nota que os clientes dão para a limpeza da mesa e do salão: <strong>${num(m)} / 5</strong> (${inteiro(av.respostas)} resposta(s)${soReais ? ", só da planilha" : ""}).`;
}

// ---------- tudo ----------
function desenhar(d) {
  document.getElementById("faixa-demo").hidden = !d.dados_simulados;
  desenharAlertas(d.alertas);
  desenharNumeros(d);

  const hora = (h) => `${h}h`;
  G.barrasH(document.getElementById("g-mix"), d.mix_itens.slice(0, 10), {
    titulo: "Participação no peso e no custo por item", rotulo: "item", nomeRotulo: "Item", fmt: (v) => pct(v, 1), fmtEixo: (v) => pct(v),
    series: [{ chave: "pct_peso", nome: "% do peso servido", cor: COR.azul }, { chave: "pct_custo", nome: "% do custo da comida", cor: COR.laranja }],
    extraDica: (l) => `<div class="linha"><span>Custo no período</span><strong>${reais(l.custo_total)}</strong></div>`,
  });
  desenharItens(d.mix_itens);
  desenharRaioX(d.raio_x);

  const horas = d.por_hora.filter((h) => h.clientes >= 5);
  G.colunas(document.getElementById("g-fila"), horas, {
    titulo: "Minutos da entrada até a balança por hora", x: "hora", nomeX: "Hora", fmtX: hora, fmt: (v) => num(v), fmtEixo: (v) => num(v, 0),
    serie: { chave: "min_ate_pesar", nome: "Média (min)", cor: COR.azul },
    ponto: { chave: "min_ate_pesar_p90", nome: "1 em cada 10 espera mais que (min)", cor: COR.laranja }, rotularMaior: true,
  });
  G.colunas(document.getElementById("g-entradas"), horas, {
    titulo: "Clientes por hora de entrada", x: "hora", nomeX: "Hora", fmtX: hora, fmt: inteiro, passoMin: 1,
    serie: { chave: "clientes", nome: "Clientes", cor: COR.azul }, rotularMaior: true,
  });

  desenharMapa(d.mesas_agora);
  G.barrasH(document.getElementById("g-saloes"), d.saloes.filter((s) => s.limpezas), {
    titulo: "Minutos de mesa suja por salão", rotulo: "salao", nomeRotulo: "Salão", fmt: (v) => num(v) + " min", fmtEixo: (v) => num(v, 0),
    margemEsq: 80, series: [{ chave: "min_mesa_suja", nome: "Média", cor: COR.azul }],
    ponto: { chave: "p90", nome: "1 em cada 10 passa de", cor: COR.laranja },
    extraDica: (l) => `<div class="linha"><span>Limpezas medidas</span><strong>${inteiro(l.limpezas)}</strong></div>`,
  });
  G.colunas(document.getElementById("g-suja-hora"), d.por_hora.filter((h) => h.limpezas >= 5), {
    titulo: "Minutos de mesa suja por hora", x: "hora", nomeX: "Hora", fmtX: hora, fmt: (v) => num(v), fmtEixo: (v) => num(v, 0), altura: 180,
    serie: { chave: "min_mesa_suja", nome: "Média (min)", cor: COR.azul }, rotularMaior: true,
  });

  const av = d.avaliacoes;
  G.divergente(document.getElementById("g-opiniao"), av.opiniao_itens.slice(0, 12), {
    titulo: "Elogios e críticas por item", rotulo: "item",
    neg: { chave: "nao_gostou", nome: "Não estava bom", cor: COR.neg }, pos: { chave: "gostou", nome: "Mais gostei", cor: COR.azul },
  });
  G.colunas(document.getElementById("g-espera-nota"), av.espera_vs_nota, {
    titulo: "Minutos até a balança por nota de espera", x: "nota", nomeX: "Nota de espera", fmtX: (n) => `Nota ${n}`, fmt: (v) => num(v), fmtEixo: (v) => num(v, 0), altura: 180,
    serie: { chave: "min_medio", nome: "Minutos até a balança", cor: COR.azul }, rotularMaior: true,
    vazio: "Sem respostas ligadas a uma comanda. Para este gráfico, o formulário precisa pedir o número da comanda.",
    extraDica: (l) => `<div class="linha"><span>Respostas</span><strong>${inteiro(l.n)}</strong></div>`,
  });
  const dist = [5, 4, 3, 2, 1].map((n) => ({ nota: `Nota ${n}`, comida: av.distribuicao.comida[n - 1],
    espera: av.distribuicao.espera[n - 1], limpeza: av.distribuicao.limpeza[n - 1] }));
  G.barrasH(document.getElementById("g-notas"), av.respostas ? dist : [], {
    titulo: "Distribuição das notas", rotulo: "nota", nomeRotulo: "Nota", fmt: inteiro, margemEsq: 70, passoMin: 1,
    series: [{ chave: "comida", nome: "Comida", cor: COR.azul }, { chave: "espera", nome: "Tempo de espera", cor: COR.laranja },
      { chave: "limpeza", nome: "Limpeza", cor: COR.aqua }],
  });
  G.barrasH(document.getElementById("g-temas"), av.temas, {
    titulo: "Assunto dos comentários", rotulo: "tema", nomeRotulo: "Assunto", fmt: inteiro, margemEsq: 100, rotularPontas: true,
    passoMin: 1, vazio: "Nenhum comentário no período.",
    series: [{ chave: "n", nome: "Comentários", cor: COR.azul }],
  });
  G.barrasH(document.getElementById("g-motivos"), av.motivos, {
    titulo: "O que não estava bom nos itens", rotulo: "motivo", nomeRotulo: "Motivo", fmt: inteiro, margemEsq: 120, rotularPontas: true,
    passoMin: 1, vazio: "Nenhum item criticado no período.",
    series: [{ chave: "n", nome: "Respostas", cor: COR.azul }],
  });
  desenharComentarios(av.comentarios);
  desenharFonte(d);

  const p = d.periodo;
  document.getElementById("subtitulo").textContent =
    `${dias === 1 ? "Hoje" : `Últimos ${dias} dias`} (${p.inicio.slice(8, 10)}/${p.inicio.slice(5, 7)} a hoje). Atualiza sozinho a cada minuto.`;
  document.getElementById("atualizado").textContent = `Atualizado às ${d.gerado_em.slice(11, 16)}`;
}

async function carregar() {
  try {
    const resp = await fetch(`/api/painel/dados?dias=${dias}${soReais ? "&reais=1" : ""}`);
    if (resp.status === 401) { location.href = "/painel/login"; return; }
    ultimo = await resp.json();
    desenhar(ultimo);
  } catch (e) {
    document.getElementById("atualizado").textContent = "Sem conexão: mostrando os últimos dados";
  }
}

const atualizarEndereco = () => history.replaceState(null, "", `?dias=${dias}${soReais ? "&reais=1" : ""}`);

document.querySelectorAll("[data-dias]").forEach((b) => {
  b.setAttribute("aria-pressed", Number(b.dataset.dias) === dias);
  b.addEventListener("click", () => {
    dias = Number(b.dataset.dias);
    document.querySelectorAll("[data-dias]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    atualizarEndereco();
    carregar();
  });
});

document.querySelectorAll("[data-reais]").forEach((b) => {
  b.setAttribute("aria-pressed", (b.dataset.reais === "1") === soReais);
  b.addEventListener("click", () => {
    soReais = b.dataset.reais === "1";
    document.querySelectorAll("[data-reais]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    atualizarEndereco();
    carregar();
  });
});

document.getElementById("sincronizar").addEventListener("click", async (e) => {
  const botao = e.currentTarget;
  botao.disabled = true;
  botao.textContent = "Sincronizando…";
  try {
    await fetch("/api/painel/sincronizar", { method: "POST" });
  } catch (erro) { /* sem conexão: o texto da fonte mostra o erro */ }
  botao.disabled = false;
  botao.textContent = "Sincronizar agora";
  carregar();
});

let espera;
addEventListener("resize", () => {
  clearTimeout(espera);
  espera = setTimeout(() => ultimo && desenhar(ultimo), 200);
});

carregar();
setInterval(carregar, ATUALIZAR_A_CADA_MS);
