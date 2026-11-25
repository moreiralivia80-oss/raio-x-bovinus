// Abre e fecha o menu no celular
const botao = document.querySelector(".menu-botao");
const menu = document.getElementById("menu");

if (botao && menu) {
  botao.addEventListener("click", () => {
    const aberto = menu.classList.toggle("aberto");
    botao.setAttribute("aria-expanded", aberto);
    botao.textContent = aberto ? "Fechar" : "Menu";
  });
}
