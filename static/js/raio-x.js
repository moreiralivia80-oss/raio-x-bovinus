// Raio-X do Prato: câmera, envio da foto e exibição do resultado.
//
// Câmera:
// - Se o navegador permite (HTTPS ou localhost), a câmera aparece ao vivo na tela.
// - Se não permite (ex.: celular acessando por http://IP), "Tirar foto" abre a câmera do próprio celular.

const video = document.getElementById("video");
const foto = document.getElementById("foto");
const aviso = document.getElementById("camera-aviso");
const btnCapturar = document.getElementById("btn-capturar");
const arquivo = document.getElementById("arquivo");
const cameraNativa = document.getElementById("camera-nativa");
const peso = document.getElementById("peso");
const erro = document.getElementById("erro");
const btnAnalisar = document.getElementById("btn-analisar");

const LADO_MAXIMO = 1280; // reduz a foto antes de enviar (mais rápido no 4G)
let fotoBlob = null;
let cameraAoVivo = false;

const reais = (v) => v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

// ---------- câmera ----------

async function ligarCamera() {
  if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
    aviso.textContent = "Toque em Tirar foto para abrir a câmera do aparelho.";
    return;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: "environment" }, width: { ideal: 1280 }, height: { ideal: 960 } },
      audio: false,
    });
    video.srcObject = stream;
    video.hidden = false;
    cameraAoVivo = true;
    aviso.textContent = "Enquadre só o prato e toque em Tirar foto.";
  } catch (e) {
    aviso.textContent = "Sem acesso à câmera. Toque em Tirar foto ou Enviar foto.";
  }
}

function mostrarFoto(blob) {
  fotoBlob = blob;
  foto.src = URL.createObjectURL(blob);
  foto.hidden = false;
  video.hidden = true;
  btnCapturar.textContent = "Tirar outra";
  aviso.textContent = "Foto pronta. Confira o peso e toque em Analisar prato.";
  limparErro();
}

function voltarParaCamera() {
  fotoBlob = null;
  foto.hidden = true;
  video.hidden = false;
  btnCapturar.textContent = "Tirar foto";
  aviso.textContent = "Enquadre só o prato e toque em Tirar foto.";
}

btnCapturar.addEventListener("click", () => {
  if (!cameraAoVivo) {
    cameraNativa.click(); // abre a câmera do celular
    return;
  }
  if (fotoBlob) {
    voltarParaCamera();
    return;
  }
  if (!video.videoWidth) return;
  const canvas = document.createElement("canvas");
  const escala = Math.min(1, LADO_MAXIMO / Math.max(video.videoWidth, video.videoHeight));
  canvas.width = Math.round(video.videoWidth * escala);
  canvas.height = Math.round(video.videoHeight * escala);
  canvas.getContext("2d").drawImage(video, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(mostrarFoto, "image/jpeg", 0.85);
});

async function reduzirImagem(file) {
  try {
    const img = await createImageBitmap(file);
    const escala = Math.min(1, LADO_MAXIMO / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * escala);
    canvas.height = Math.round(img.height * escala);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    return await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.85));
  } catch (e) {
    return file; // se não conseguir reduzir, envia a original
  }
}

for (const entrada of [arquivo, cameraNativa]) {
  entrada.addEventListener("change", async () => {
    if (!entrada.files[0]) return;
    aviso.textContent = "Preparando a foto...";
    mostrarFoto(await reduzirImagem(entrada.files[0]));
    entrada.value = "";
  });
}

// ---------- análise ----------

function mostrarErro(texto) {
  erro.textContent = texto;
  erro.hidden = false;
}

function limparErro() {
  erro.hidden = true;
}

peso.addEventListener("input", limparErro);

function estado(nome) {
  document.getElementById("resultado-vazio").hidden = nome !== "vazio";
  document.getElementById("resultado-carregando").hidden = nome !== "carregando";
  document.getElementById("resultado-conteudo").hidden = nome !== "conteudo";
}

btnAnalisar.addEventListener("click", async () => {
  if (!fotoBlob) return mostrarErro("Tire ou envie a foto do prato.");
  const gramas = Number(peso.value);
  if (!gramas || gramas <= 0) {
    peso.focus();
    return mostrarErro("Informe o peso do prato em gramas.");
  }
  limparErro();
  estado("carregando");
  btnAnalisar.disabled = true;
  btnAnalisar.textContent = "Analisando...";

  const form = new FormData();
  form.append("foto", fotoBlob, "prato.jpg");
  form.append("peso_g", gramas);

  try {
    const resp = await fetch("/api/raio-x/analisar", { method: "POST", body: form });
    const dados = await resp.json();
    if (!resp.ok) {
      estado("vazio");
      mostrarErro(dados.erro || "Não foi possível analisar o prato.");
      return;
    }
    renderizar(dados);
  } catch (e) {
    estado("vazio");
    mostrarErro("Sem conexão com o servidor. Verifique a internet e tente de novo.");
  } finally {
    btnAnalisar.disabled = false;
    btnAnalisar.textContent = "Analisar prato";
  }
});

function nivel(valor) {
  if (valor >= 80) return { classe: "alta", texto: "alta" };
  if (valor >= 60) return { classe: "media", texto: "média" };
  return { classe: "baixa", texto: "baixa" };
}

function renderizar(r) {
  const origem = document.getElementById("origem");
  origem.hidden = false;
  origem.textContent = r.origem === "ia" ? "Analisado pela IA" : "Demonstração";
  origem.className = "selo" + (r.origem === "ia" ? " selo--ia" : "");

  if (!r.e_prato_de_comida || r.itens.length === 0) {
    estado("vazio");
    mostrarErro(r.observacao || "Não foi possível identificar comida nesta foto. Tire outra foto do prato.");
    return;
  }

  const n = nivel(r.precisao);
  document.getElementById("precisao").className = "precisao precisao--" + n.classe;
  document.getElementById("precisao-valor").textContent = `${r.precisao}% (${n.texto})`;
  document.getElementById("precisao-barra").style.width = r.precisao + "%";
  document.getElementById("precisao-texto").textContent =
    n.classe === "baixa" ? "Precisão baixa: tire outra foto, mais de cima e com boa luz." : "";

  document.getElementById("r-receita").textContent = reais(r.receita);
  document.getElementById("r-custo").textContent = reais(r.custo_estimado);
  document.getElementById("r-margem").textContent =
    r.margem === null ? "–" : (r.margem * 100).toFixed(1).replace(".", ",") + "%";

  document.getElementById("r-itens").innerHTML = r.itens.map((i) => {
    const c = nivel(i.confianca);
    const nome = i.nome.replace(/[<>&]/g, "");
    return `<tr>
      <td>${nome}${i.custo_conhecido ? "" : ' <span class="item-novo" title="Custo estimado pela categoria">*</span>'}</td>
      <td><span class="barra" style="--p:${i.percentual}%"></span>${String(i.percentual).replace(".", ",")}%</td>
      <td><span class="certeza certeza--${c.classe}">${i.confianca}%</span></td>
      <td>${reais(i.custo)}</td>
    </tr>`;
  }).join("");

  const temNovo = r.itens.some((i) => !i.custo_conhecido);
  document.getElementById("r-observacao").textContent =
    [r.aviso, r.observacao, temNovo ? "* Item fora da lista: custo estimado pela categoria." : ""]
      .filter(Boolean).join(" ");

  estado("conteudo");
  if (window.innerWidth < 760) {
    document.getElementById("titulo-resultado").scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

ligarCamera();
