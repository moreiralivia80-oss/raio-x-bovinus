// Fila offline das telas de operação (estação de pip e mesas do garçom).
//
// Com conexão: envia na hora e o servidor usa o relógio DELE (todos os pontos com a mesma hora).
// Sem conexão (Wi-Fi caiu, computador desligado): guarda o toque NO APARELHO com a hora do toque
// e reenvia sozinho a cada 10 s. Cada toque leva um id único, então um reenvio nunca conta duas vezes.

const Fila = (() => {
  const CHAVE = "bovinus_fila";
  const ler = () => { try { return JSON.parse(localStorage.getItem(CHAVE) || "[]"); } catch (e) { return []; } };
  const salvar = (f) => localStorage.setItem(CHAVE, JSON.stringify(f));
  const ouvintes = [];
  const avisar = () => ouvintes.forEach((f) => f(ler().length));

  function agoraTexto() {
    const d = new Date(), p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
  }
  const novoId = () => (window.crypto && crypto.randomUUID ? crypto.randomUUID()
    : Date.now().toString(36) + Math.random().toString(36).slice(2));

  async function postar(url, corpo) {
    const resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) });
    let dados = {};
    try { dados = await resp.json(); } catch (e) { /* resposta vazia */ }
    return { ok: resp.ok, status: resp.status, dados };
  }

  // Devolve {ok, status, dados} quando o servidor respondeu, ou {offline: true, id, naFila} quando guardou.
  async function enviar(url, corpo) {
    const id = novoId();
    corpo = { id_cliente: id, ...corpo };
    try {
      return await postar(url, corpo);
    } catch (e) {
      const f = ler();
      f.push({ url, corpo: { ...corpo, momento: agoraTexto() }, guardado_em: Date.now() });
      salvar(f);
      avisar();
      return { offline: true, id, naFila: f.length };
    }
  }

  // Tira da fila um toque que ainda não foi enviado (botão "Desfazer" sem conexão).
  function remover(id) {
    const f = ler(), antes = f.length;
    salvar(f.filter((x) => x.corpo.id_cliente !== id));
    avisar();
    return ler().length < antes;
  }

  let enviando = false;
  async function reenviar() {
    if (enviando) return;
    enviando = true;
    try {
      while (ler().length) {
        const item = ler()[0];
        try {
          await postar(item.url, item.corpo);
        } catch (e) {
          break; // continua sem conexão: tenta de novo depois
        }
        // enviado (ou recusado pelo servidor, ex.: mesa inexistente): sai da fila
        salvar(ler().filter((x) => x.corpo.id_cliente !== item.corpo.id_cliente));
        avisar();
      }
    } finally {
      enviando = false;
    }
  }

  setInterval(reenviar, 10_000);
  addEventListener("online", reenviar);
  setTimeout(reenviar, 500);

  return {
    enviar, remover, reenviar,
    tamanho: () => ler().length,
    aoMudar: (f) => { ouvintes.push(f); f(ler().length); },
  };
})();
