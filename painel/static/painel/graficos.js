// Gráficos do painel em SVG puro (sem biblioteca externa: funciona sem internet).
// Regras de desenho: barras finas (até 24px) com ponta arredondada e base reta, grade fina,
// legenda sempre que houver 2+ séries, dica (tooltip) ao passar o mouse e tabela com os números.

const G = (() => {
  const dica = () => document.getElementById("dica");
  const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  function escalaBonita(max, passos = 4, passoMin = 0) {
    if (!max || max <= 0) return { max: Math.max(1, passoMin), passo: Math.max(0.25, passoMin) };
    if (passoMin && max / passos < passoMin) return { max: Math.ceil(max / passoMin) * passoMin, passo: passoMin };
    const bruto = max / passos;
    const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const passo = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((p) => p >= bruto);
    return { max: Math.ceil(max / passo) * passo, passo };
  }

  // barra horizontal: base reta à esquerda, ponta arredondada à direita
  function barraH(x, y, w, h, r = 4) {
    if (w <= 0) return "";
    r = Math.min(r, w, h / 2);
    return `M${x},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h - r}Q${x + w},${y + h} ${x + w - r},${y + h}H${x}Z`;
  }
  // barra horizontal para a esquerda (lado negativo do gráfico divergente)
  function barraHEsq(x, y, w, h, r = 4) {
    if (w <= 0) return "";
    r = Math.min(r, w, h / 2);
    return `M${x},${y}H${x - w + r}Q${x - w},${y} ${x - w},${y + r}V${y + h - r}Q${x - w},${y + h} ${x - w + r},${y + h}H${x}Z`;
  }
  // coluna: base reta embaixo, ponta arredondada em cima
  function coluna(x, base, w, h, r = 4) {
    if (h <= 0) return "";
    r = Math.min(r, h, w / 2);
    return `M${x},${base}V${base - h + r}Q${x},${base - h} ${x + r},${base - h}H${x + w - r}Q${x + w},${base - h} ${x + w},${base - h + r}V${base}Z`;
  }

  function legenda(itens) {
    if (itens.length < 2) return "";
    return `<ul class="legenda">${itens.map((s) =>
      `<li><i class="${s.ponto ? "ponto" : ""}" style="background:${s.cor}"></i>${esc(s.nome)}</li>`).join("")}</ul>`;
  }

  function tabela(colunas, linhas) {
    const cab = colunas.map((c) => `<th class="${c.num ? "num" : ""}" scope="col">${esc(c.nome)}</th>`).join("");
    const corpo = linhas.map((l) => `<tr>${colunas.map((c) =>
      `<td class="${c.num ? "num" : ""}">${esc(c.fmt ? c.fmt(l[c.chave], l) : l[c.chave])}</td>`).join("")}</tr>`).join("");
    return `<details class="tabela-dados"><summary>Ver tabela</summary><table class="dados"><thead><tr>${cab}</tr></thead><tbody>${corpo}</tbody></table></details>`;
  }

  function ligarDicas(el, montarTexto) {
    const d = dica();
    el.querySelectorAll("[data-i]").forEach((alvo) => {
      const mostrar = (ev) => {
        d.innerHTML = montarTexto(Number(alvo.dataset.i));
        d.hidden = false;
        const r = d.getBoundingClientRect();
        let x = (ev.clientX ?? alvo.getBoundingClientRect().right) + 14;
        let y = (ev.clientY ?? alvo.getBoundingClientRect().top) + 14;
        if (x + r.width > innerWidth - 8) x = x - r.width - 28;
        if (y + r.height > innerHeight - 8) y = y - r.height - 28;
        d.style.left = x + "px";
        d.style.top = y + "px";
        el.querySelectorAll(`.marca[data-g="${alvo.dataset.i}"]`).forEach((m) => m.classList.add("ativa"));
      };
      const esconder = () => {
        d.hidden = true;
        el.querySelectorAll(".marca.ativa").forEach((m) => m.classList.remove("ativa"));
      };
      alvo.addEventListener("mousemove", mostrar);
      alvo.addEventListener("focus", mostrar);
      alvo.addEventListener("mouseleave", esconder);
      alvo.addEventListener("blur", esconder);
    });
  }

  function linhaDica(cor, nome, valor, ponto) {
    return `<div class="linha"><span><i style="background:${cor};${ponto ? "border-radius:50%" : ""}"></i>${esc(nome)}</span><strong>${esc(valor)}</strong></div>`;
  }

  // ---------------------------------------------------------------- barras horizontais
  // linhas: [{...}], op: {rotulo, series:[{chave,nome,cor}], ponto:{chave,nome,cor}, fmt, rotularPontas}
  function barrasH(el, linhas, op) {
    if (!linhas.length) { el.innerHTML = `<p class="vazio">${esc(op.vazio || "Sem dados no período.")}</p>`; return; }
    const larg = Math.max(280, el.clientWidth);
    const esq = op.margemEsq ?? 130, dir = 48, topo = 6, baixo = 22;
    const n = op.series.length;
    const esp = n > 1 ? 10 : 16, gap = 2;
    const banda = n * esp + (n - 1) * gap + 14;
    const alt = topo + linhas.length * banda + baixo;
    const vals = linhas.flatMap((l) => [...op.series.map((s) => l[s.chave] ?? 0), op.ponto ? l[op.ponto.chave] ?? 0 : 0]);
    const esc_ = escalaBonita(Math.max(...vals), 4, op.passoMin || 0);
    const w = larg - esq - dir;
    const X = (v) => esq + (v / esc_.max) * w;

    let svg = "";
    for (let t = 0; t <= esc_.max + 1e-9; t += esc_.passo) {
      svg += `<line class="grade-linha" x1="${X(t)}" x2="${X(t)}" y1="${topo}" y2="${alt - baixo}"/>`;
      svg += `<text x="${X(t)}" y="${alt - 6}" text-anchor="middle">${esc(op.fmtEixo ? op.fmtEixo(t) : op.fmt(t))}</text>`;
    }
    linhas.forEach((l, i) => {
      const y0 = topo + i * banda + 7;
      svg += `<text class="rot-cat" x="${esq - 10}" y="${y0 + (banda - 14) / 2 + 4}" text-anchor="end">${esc(l[op.rotulo])}</text>`;
      op.series.forEach((s, k) => {
        const y = y0 + k * (esp + gap);
        svg += `<path class="marca" data-g="${i}" fill="${s.cor}" d="${barraH(esq, y, X(l[s.chave] ?? 0) - esq, esp)}"/>`;
        if (op.rotularPontas) {
          svg += `<text class="rot-valor" x="${X(l[s.chave] ?? 0) + 6}" y="${y + esp / 2 + 4}">${esc(op.fmt(l[s.chave]))}</text>`;
        }
      });
      if (op.ponto && l[op.ponto.chave] != null) {
        const cy = y0 + esp / 2;
        svg += `<circle class="marca" data-g="${i}" cx="${X(l[op.ponto.chave])}" cy="${cy}" r="5" fill="${op.ponto.cor}" stroke="var(--superficie)" stroke-width="2"/>`;
      }
      svg += `<rect class="alvo" data-i="${i}" tabindex="0" x="0" y="${y0 - 6}" width="${larg}" height="${banda}"/>`;
    });
    svg += `<line class="eixo-linha" x1="${esq}" x2="${esq}" y1="${topo}" y2="${alt - baixo}"/>`;

    const itensLeg = [...op.series, ...(op.ponto ? [{ ...op.ponto, ponto: true }] : [])];
    el.innerHTML = legenda(itensLeg) +
      `<svg viewBox="0 0 ${larg} ${alt}" role="img" aria-label="${esc(op.titulo || "")}">${svg}</svg>` +
      tabela([{ chave: op.rotulo, nome: op.nomeRotulo || "" }, ...itensLeg.map((s) => ({ chave: s.chave, nome: s.nome, num: true, fmt: op.fmt }))], linhas);
    ligarDicas(el, (i) => `<b>${esc(linhas[i][op.rotulo])}</b>` +
      itensLeg.map((s) => linhaDica(s.cor, s.nome, op.fmt(linhas[i][s.chave]), s.ponto)).join("") + (op.extraDica ? op.extraDica(linhas[i]) : ""));
  }

  // ---------------------------------------------------------------- colunas
  // op: {x, fmtX, serie:{chave,nome,cor}, ponto:{chave,nome,cor}, fmt, rotularMaior}
  function colunas(el, linhas, op) {
    if (!linhas.length) { el.innerHTML = `<p class="vazio">${esc(op.vazio || "Sem dados no período.")}</p>`; return; }
    const larg = Math.max(280, el.clientWidth);
    const esq = 40, dir = 8, topo = 18, baixo = 26, alt = op.altura || 220;
    const vals = linhas.flatMap((l) => [l[op.serie.chave] ?? 0, op.ponto ? l[op.ponto.chave] ?? 0 : 0]);
    const e = escalaBonita(Math.max(...vals), 4, op.passoMin || 0);
    const w = larg - esq - dir, h = alt - topo - baixo;
    const banda = w / linhas.length;
    const bw = Math.min(24, banda * 0.6);
    const Y = (v) => topo + h - (v / e.max) * h;
    const base = topo + h;

    let svg = "";
    for (let t = 0; t <= e.max + 1e-9; t += e.passo) {
      svg += `<line class="grade-linha" x1="${esq}" x2="${larg - dir}" y1="${Y(t)}" y2="${Y(t)}"/>`;
      svg += `<text x="${esq - 6}" y="${Y(t) + 4}" text-anchor="end">${esc(op.fmtEixo ? op.fmtEixo(t) : op.fmt(t))}</text>`;
    }
    const maior = linhas.reduce((m, l, i) => ((l[op.serie.chave] ?? -1) > (linhas[m][op.serie.chave] ?? -1) ? i : m), 0);
    linhas.forEach((l, i) => {
      const cx = esq + banda * i + banda / 2;
      const v = l[op.serie.chave];
      if (v != null) svg += `<path class="marca" data-g="${i}" fill="${op.serie.cor}" d="${coluna(cx - bw / 2, base, bw, base - Y(v))}"/>`;
      if (op.ponto && l[op.ponto.chave] != null) {
        svg += `<circle class="marca" data-g="${i}" cx="${cx}" cy="${Y(l[op.ponto.chave])}" r="5" fill="${op.ponto.cor}" stroke="var(--superficie)" stroke-width="2"/>`;
      }
      if (op.rotularMaior && i === maior && v != null) {
        // com ponto (p90) acima, o valor vai ao lado da coluna para não colidir
        svg += `<text class="rot-valor" x="${cx + (op.ponto ? bw / 2 + 4 : 0)}" y="${Y(v) + (op.ponto ? 12 : -6)}" text-anchor="${op.ponto ? "start" : "middle"}">${esc(op.fmt(v))}</text>`;
      }
      svg += `<text x="${cx}" y="${alt - 8}" text-anchor="middle">${esc(op.fmtX ? op.fmtX(l[op.x]) : l[op.x])}</text>`;
      svg += `<rect class="alvo" data-i="${i}" tabindex="0" x="${esq + banda * i}" y="${topo}" width="${banda}" height="${h}"/>`;
    });
    svg += `<line class="eixo-linha" x1="${esq}" x2="${larg - dir}" y1="${base}" y2="${base}"/>`;

    const itensLeg = [op.serie, ...(op.ponto ? [{ ...op.ponto, ponto: true }] : [])];
    el.innerHTML = legenda(itensLeg) +
      `<svg viewBox="0 0 ${larg} ${alt}" role="img" aria-label="${esc(op.titulo || "")}">${svg}</svg>` +
      tabela([{ chave: op.x, nome: op.nomeX || "", fmt: op.fmtX }, ...itensLeg.map((s) => ({ chave: s.chave, nome: s.nome, num: true, fmt: op.fmt }))], linhas);
    ligarDicas(el, (i) => `<b>${esc(op.fmtX ? op.fmtX(linhas[i][op.x]) : linhas[i][op.x])}</b>` +
      itensLeg.map((s) => linhaDica(s.cor, s.nome, op.fmt(linhas[i][s.chave]), s.ponto)).join("") + (op.extraDica ? op.extraDica(linhas[i]) : ""));
  }

  // ---------------------------------------------------------------- divergente (críticas <- | -> elogios)
  function divergente(el, linhas, op) {
    if (!linhas.length) { el.innerHTML = '<p class="vazio">Sem avaliações no período.</p>'; return; }
    const larg = Math.max(300, el.clientWidth);
    const rot = 120, topo = 6, baixo = 22, esp = 14, banda = 24;
    const alt = topo + linhas.length * banda + baixo;
    const maxNeg = Math.max(...linhas.map((l) => l[op.neg.chave]));
    const maxPos = Math.max(...linhas.map((l) => l[op.pos.chave]));
    const e = escalaBonita(Math.max(maxNeg, maxPos), 3, 1);
    const area = larg - rot - 16;
    const meio = rot + area / 2;
    const S = (v) => (v / e.max) * (area / 2 - 28);

    let svg = "";
    for (let t = e.passo; t <= e.max + 1e-9; t += e.passo) {
      for (const lado of [-1, 1]) {
        svg += `<line class="grade-linha" x1="${meio + lado * S(t)}" x2="${meio + lado * S(t)}" y1="${topo}" y2="${alt - baixo}"/>`;
        svg += `<text x="${meio + lado * S(t)}" y="${alt - 6}" text-anchor="middle">${t}</text>`;
      }
    }
    linhas.forEach((l, i) => {
      const y = topo + i * banda + (banda - esp) / 2;
      svg += `<text class="rot-cat" x="${rot - 10}" y="${y + esp / 2 + 4}" text-anchor="end">${esc(l[op.rotulo])}</text>`;
      svg += `<path class="marca" data-g="${i}" fill="${op.neg.cor}" d="${barraHEsq(meio - 1, y, S(l[op.neg.chave]), esp)}"/>`;
      svg += `<path class="marca" data-g="${i}" fill="${op.pos.cor}" d="${barraH(meio + 1, y, S(l[op.pos.chave]), esp)}"/>`;
      if (l[op.neg.chave]) svg += `<text class="rot-valor" x="${meio - 1 - S(l[op.neg.chave]) - 6}" y="${y + esp / 2 + 4}" text-anchor="end">${l[op.neg.chave]}</text>`;
      if (l[op.pos.chave]) svg += `<text class="rot-valor" x="${meio + 1 + S(l[op.pos.chave]) + 6}" y="${y + esp / 2 + 4}">${l[op.pos.chave]}</text>`;
      svg += `<rect class="alvo" data-i="${i}" tabindex="0" x="0" y="${topo + i * banda}" width="${larg}" height="${banda}"/>`;
    });
    svg += `<line class="eixo-linha" x1="${meio}" x2="${meio}" y1="${topo}" y2="${alt - baixo}"/>`;

    el.innerHTML = legenda([op.neg, op.pos]) +
      `<svg viewBox="0 0 ${larg} ${alt}" role="img" aria-label="${esc(op.titulo || "")}">${svg}</svg>` +
      tabela([{ chave: op.rotulo, nome: "Item" }, { chave: op.neg.chave, nome: op.neg.nome, num: true }, { chave: op.pos.chave, nome: op.pos.nome, num: true }], linhas);
    ligarDicas(el, (i) => `<b>${esc(linhas[i][op.rotulo])}</b>` +
      linhaDica(op.pos.cor, op.pos.nome, linhas[i][op.pos.chave]) + linhaDica(op.neg.cor, op.neg.nome, linhas[i][op.neg.chave]));
  }

  return { barrasH, colunas, divergente, esc };
})();
