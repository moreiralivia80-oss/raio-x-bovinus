// Tela do garçom: um toque marca "cliente saiu" (vermelha), outro marca "limpa" (verde).
// Funciona sem conexão: o toque fica guardado no aparelho (fila.js) e é enviado depois.

const NOMES_SALAO = { Inferior: "Salão Inferior (pista)", Principal: "Salão Principal", Superior: "Salão Superior" };
const ATUALIZAR_MS = 10_000;
const DESFAZER_MS = 120_000;

let mesas = [];
let salao = localStorage.getItem("bovinus_salao") || "Todos";
let ultimoToque = null; // {numero, acao, id, offline, quando, anterior}

const $ = (id) => document.getElementById(id);

function classe(m) {
  if (m.status === "ocupada") return "mesa--ocupada";
  if (m.status !== "suja") return "mesa--livre";
  return m.minutos < 5 ? "mesa--suja-1" : m.minutos < 10 ? "mesa--suja-2" : "mesa--suja-3";
}

function texto(m) {
  if (m.status === "suja") return `suja ${m.minutos} min`;
  return m.status === "ocupada" ? "ocupada" : "livre";
}

function desenhar() {
  const visiveis = salao === "Todos" ? Object.keys(NOMES_SALAO) : [salao];
  $("saloes").innerHTML = visiveis.map((s) => {
    const doSalao = mesas.filter((m) => m.salao === s);
    const sujas = doSalao.filter((m) => m.status === "suja").length;
    return `<section class="garcom__salao">
      <h2>${NOMES_SALAO[s]} <span>${sujas} suja(s)</span></h2>
      <div class="garcom__mesas">${doSalao.map((m) => `
        <button type="button" class="mesa-g ${classe(m)}" data-n="${m.numero}"
          aria-label="Mesa ${m.numero}, ${texto(m)}. Tocar para marcar ${m.status === "suja" ? "limpa" : "cliente saiu"}.">
          <strong>${m.numero}</strong><small>${texto(m)}</small>
        </button>`).join("")}</div>
    </section>`;
  }).join("");
  const sujas = mesas.filter((m) => m.status === "suja").length;
  $("contagem").textContent = `${sujas} mesa(s) suja(s) no salão`;
}

async function carregar() {
  try {
    const resp = await fetch("/api/mesas");
    if (!resp.ok) throw new Error();
    const servidor = await resp.json();
    // toques ainda na fila continuam valendo na tela até serem enviados
    const pendentes = {};
    for (const item of JSON.parse(localStorage.getItem("bovinus_fila") || "[]")) {
      const achado = item.url.match(/\/api\/mesas\/(\d+)\/(saiu|limpa)/);
      if (achado) pendentes[achado[1]] = achado[2];
    }
    mesas = servidor.map((m) => {
      const p = pendentes[m.numero];
      if (p === "saiu") return { ...m, status: "suja", minutos: m.minutos ?? 0 };
      if (p === "limpa") return { ...m, status: "livre", minutos: null };
      return m;
    });
    desenhar();
  } catch (e) {
    // sem conexão: mantém o último mapa na tela
  }
}

function avisar(textoAviso) {
  $("aviso-texto").textContent = textoAviso;
  $("aviso").hidden = false;
  clearTimeout(avisar.t);
  avisar.t = setTimeout(() => { $("aviso").hidden = true; }, 8000);
}

async function tocar(numero) {
  const m = mesas.find((x) => x.numero === numero);
  if (!m) return;
  const acao = m.status === "suja" ? "limpa" : "saiu";
  const anterior = { ...m };
  // atualiza a tela na hora (não espera a rede)
  Object.assign(m, acao === "saiu" ? { status: "suja", minutos: 0 } : { status: "livre", minutos: null });
  desenhar();
  if (navigator.vibrate && navigator.userActivation && navigator.userActivation.isActive) navigator.vibrate(30);

  const r = await Fila.enviar(`/api/mesas/${numero}/${acao}`, {});
  ultimoToque = { numero, acao, id: r.id, offline: !!r.offline, quando: Date.now(), anterior };
  if (!r.offline && !r.ok) {
    Object.assign(m, anterior);
    desenhar();
    avisar(r.dados.erro || "Não foi possível registrar. Tente de novo.");
    ultimoToque = null;
    return;
  }
  const feito = acao === "saiu" ? "marcada suja" : `marcada limpa${r.dados && r.dados.minutos_suja != null ? ` (ficou ${String(r.dados.minutos_suja).replace(".", ",")} min suja)` : ""}`;
  avisar(`Mesa ${numero} ${feito}${r.offline ? " — guardado sem conexão" : ""}.`);
}

async function desfazer() {
  const t = ultimoToque;
  if (!t || Date.now() - t.quando > DESFAZER_MS) { $("aviso").hidden = true; return; }
  if (t.offline && Fila.remover(t.id)) {
    // ainda não tinha saído do aparelho: basta tirar da fila
  } else {
    const r = await Fila.enviar(`/api/mesas/${t.numero}/desfazer`, {});
    if (!r.offline && !r.ok) { avisar(r.dados.erro || "Não deu para desfazer."); return; }
  }
  const m = mesas.find((x) => x.numero === t.numero);
  if (m) Object.assign(m, t.anterior);
  ultimoToque = null;
  desenhar();
  avisar(`Mesa ${t.numero}: toque desfeito.`);
}

document.querySelectorAll("[data-salao]").forEach((b) => {
  b.setAttribute("aria-pressed", b.dataset.salao === salao);
  b.addEventListener("click", () => {
    salao = b.dataset.salao;
    localStorage.setItem("bovinus_salao", salao);
    document.querySelectorAll("[data-salao]").forEach((x) => x.setAttribute("aria-pressed", x === b));
    desenhar();
  });
});
$("saloes").addEventListener("click", (e) => {
  const botao = e.target.closest("[data-n]");
  if (botao) tocar(Number(botao.dataset.n));
});
$("desfazer").addEventListener("click", desfazer);

Fila.aoMudar((n) => {
  $("conexao").textContent = n ? `Sem conexão: ${n} toque(s) guardado(s)` : "";
  $("conexao").className = "conexao" + (n ? " conexao--fila" : "");
});

carregar();
setInterval(carregar, ATUALIZAR_MS);
