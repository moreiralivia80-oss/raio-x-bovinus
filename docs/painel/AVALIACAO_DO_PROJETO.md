# Avaliação do projeto (zip `raio-x-bovinus-main`) e melhorias

## 1. O que o grupo já tem

| Parte | Situação no zip | Situação com o painel |
|---|---|---|
| Raio-X do Prato (`/raio-x`) | **Funciona.** Câmera ao vivo ou do celular, reduz a foto antes de enviar, manda para o Gemini com a lista do buffet, devolve itens, certeza por item, precisão geral, custo e margem. Tem modo demonstração quando não há chave ou a API falha. Bem feito. | Falta só gravar o resultado: 1 linha (item 5). |
| Avaliação (`/avaliacao`) | Página reservada. O formulário foi feito no **Google Forms**, fora do zip. | **Conectado.** O painel lê a planilha de respostas sozinho a cada 2 minutos. A página `/avaliacao` do app pode só redirecionar para o link do formulário. |
| Mesas (`/mesas`) | Página reservada | **Pronta no painel:** `/garcom`, com mapa dos 3 salões, um toque para "saiu" e "limpa", "Desfazer" e funcionamento sem conexão. |
| Área do gerente (`/gerente`) | Página reservada + login que não confere nada | Substituída por `/painel`, com login de verdade. |
| Identidade visual | Boa: fachada, letreiro e tijolos | O painel usa as mesmas cores e o mesmo cabeçalho; diferenças em [DOCUMENTACAO.md](DOCUMENTACAO.md#7-identidade-visual). |

## 2. Problemas encontrados (por prioridade)

1. **Depurador do Flask aberto na rede** (`app.py`, última linha: `app.run(host="0.0.0.0", ..., debug=True)`). Com `debug=True` e `0.0.0.0`, qualquer aparelho no Wi-Fi do restaurante que provoque um erro consegue abrir o console do Werkzeug e executar código no computador. Correção: `debug=os.environ.get("FLASK_DEBUG") == "1"`. O .exe do painel usa o servidor Waitress, que não tem depurador.
2. **Login do gerente não protege nada e expõe a senha.** `gerente_login.html` usa `<form action="/gerente">` sem `method="post"`: a senha vai na URL (fica no histórico e nos logs) e a rota `/gerente` abre para qualquer um. O painel resolve com login por POST, sessão assinada e comparação segura da senha.
3. **Nenhum dado é salvo.** O resumo diz "salvamos no banco", mas `api_analisar()` calcula e devolve o resultado sem gravar. Sem isso, o painel não tem o que mostrar do Raio-X. Correção: uma linha `registrar_prato_do_raio_x(resultado, comanda)` (item 5).
4. **Prato não é ligado ao cliente.** Sem o código da comanda na tela do Raio-X, não dá para medir a espera nem cruzar a nota com o tempo. Correção: campo "Comanda" ao lado do peso (ou leitor USB na balança).
5. **Formulário sem mesa e sem comanda.** A pesquisa real não pergunta a mesa nem a comanda. Por isso:
   - a nota não se liga ao tempo que o cliente realmente esperou;
   - não dá para saber de qual salão veio a nota de limpeza;
   - não dá para limitar o desconto ou cashback a 1 por comanda.

   Correção no item 5, passo 7.
6. **Nomes de itens do formulário diferentes do cadastro do buffet.** O formulário tem "Feijoada" e "Massas"; o Raio-X usa "Macarrão" e não tem "Feijoada". Esses itens aparecem nas opiniões, mas sem custo e sem presença nos pratos. Correção: usar os mesmos nomes nos dois (o painel já remove a categoria "Churrasco:" e "Prato quente:" e ignora acentos e maiúsculas).
7. **Pergunta 6 respondida sem crítica.** Na 1ª resposta real, o cliente marcou "Estava tudo bom" na pergunta 5 e mesmo assim respondeu "Outro" na 6. O painel já ignora o motivo quando nenhum item foi criticado. No formulário, deixar a pergunta 6 opcional.
8. **Custos fixos no código** (`servicos/custos.py`). O gerente não consegue atualizar o preço da picanha. A tabela `itens_buffet` do painel já tem os mesmos valores; o próximo passo é o Raio-X ler dela.
9. **Pratos de demonstração podem se misturar aos reais.** O resultado aleatório do modo demonstração precisa ficar marcado (`origem = 'demonstracao'`, que o painel já grava) e, no restaurante, a chave do Gemini precisa estar configurada.
10. **LGPD no formulário de cashback.** Se o formulário pede CPF, telefone ou e-mail para o cashback, incluir aviso de finalidade e consentimento. O painel não lê esses dados: só reconhece as perguntas da seção 5 da documentação. A câmera do Raio-X deve enquadrar só o prato; o app já não guarda a foto, o que é bom.
11. **Detalhes**: README com "[Integrante 1]" a preencher; `requirements.txt` sem versão máxima; o app não tem testes automatizados (o painel traz 32, mais o teste de ponta a ponta).

## 3. Ajustes no texto do resumo

| Trecho atual | Problema | Sugestão |
|---|---|---|
| "pandas: biblioteca Python que cria as telas web direto do código, sem precisar de HTML" | Isso descreve o **Streamlit**, não o pandas; e o projeto usa **Flask + HTML** | "Flask: servidor web em Python que entrega as telas" |
| "os gráficos prontos do  para mostrar" | Nome da ferramenta faltando | "gráficos desenhados em SVG no navegador, sem biblioteca externa" |
| "Python com pandas: cálculos" | O painel calcula com SQL (views) | "SQL no SQLite para os cálculos; as mesmas tabelas são exportadas em CSV para o sistema da casa" |
| Parte 2: "QR Code ... formulário simples ... salva com o número da mesa" | O formulário real é Google Forms e não pede a mesa | "QR Code abre o formulário do Google; o painel lê as respostas da planilha automaticamente" |
| Parte 2: "A IA lê os comentários e separa o assunto" | O painel separa por palavras-chave, sem custo | "o assunto do comentário é separado automaticamente (comida, espera, limpeza, atendimento)" |
| Parte 3 (garçom toca "cliente saiu") | Dá para automatizar metade | "a mesa fica vermelha sozinha quando a última comanda daquela mesa é paga; o garçom só toca 'limpa'" |
| Não fala de espera | Uma das dores (filas) ficou sem medição | incluir a comanda pipada (texto abaixo) |

## 4. Resumo revisado (sugestão para a entrega)

> *HACKATHON BOVINU'S - NOSSA IDEIA DE PROJETO*
>
> *O problema*
> A Bovinu'S não tem dados sobre o que acontece no salão: não sabe o que vai em cada prato (e quanto ele custa), quanto o cliente espera para se servir, quanto tempo as mesas ficam sujas e o que o cliente achou da comida.
>
> *A solução: Raio-X Bovinu'S*
> Um sistema web em Python que coleta esses dados com os gestos que a equipe e o cliente já fazem e mostra tudo num painel automático para o gerente.
>
> *1. Raio-X do Prato*
> Na balança, uma câmera fotografa o prato e a IA (Google Gemini) identifica cada item e quanto ele ocupa. Com o peso e o custo do kg de cada item, calculamos o custo e a margem de cada prato.
>
> *2. Comanda pipada (tempo de espera)*
> A comanda é entregue na entrada e lida (pipada) com um leitor de código de barras. É lida de novo na balança, pelo garçom na mesa e no caixa. Assim medimos, em minutos e sem ninguém anotar nada, quanto o cliente leva para se servir, quanto espera pelo garçom e quanto tempo fica na casa.
>
> *3. Controle das mesas*
> Quando a última comanda de uma mesa é paga, a mesa fica vermelha sozinha no celular do garçom. Ele toca "limpa" e ela fica verde. Se o Wi-Fi cair, o celular guarda os toques e envia depois. O sistema mede o tempo de mesa suja por salão e por horário.
>
> *4. Pesquisa do cliente*
> QR Code na mesa abre o formulário do Google: notas de comida, tempo de espera e limpeza, itens de que mais gostou, itens que não estavam bons e o motivo, e comentário. Quem responde ganha desconto ou cashback. O painel lê as respostas da planilha sozinho, a cada 2 minutos.
>
> *5. Painel do gerente*
> Atualiza sozinho e escreve alertas: "Picanha é 14% do peso, mas 41% do custo", "Fila às 13h passa de 10 min", "Salão Superior demora 3 min a mais para limpar", "Este item tem mais críticas que elogios". Tem mapa das mesas ao vivo e exportação em CSV para o sistema da casa.
>
> *Tecnologia*
> Python + Flask (telas e API), SQLite (banco em um arquivo), Google Gemini (fotos dos pratos), Google Forms (pesquisa), gráficos em SVG no navegador, executável para Windows. Hardware: câmera na balança e leitor de código de barras USB (R$ 80 a R$ 150 cada).

## 5. Como integrar o painel no zip

1. Copie a pasta `painel/` para dentro de `raio-x-bovinus-main/`.
2. `app.py`:

```python
import os
from flask import Flask, jsonify, redirect, render_template, request, url_for
from painel import bp as painel_bp, registrar_prato_do_raio_x
from servicos import custos, gemini

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "troque-esta-chave")
app.register_blueprint(painel_bp)

# remover as rotas /gerente e /gerente/login (o painel usa /painel e /painel/login)

@app.route("/mesas")
def mesas():
    return redirect(url_for("painel.garcom_tela"))  # a tela de mesas do painel

@app.post("/api/raio-x/analisar")
def api_analisar():
    ...
    resultado["origem"] = origem
    resultado["aviso"] = aviso
    if resultado["itens"] and resultado["e_prato_de_comida"]:
        registrar_prato_do_raio_x(resultado, request.form.get("comanda"))
    return jsonify(resultado)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)),
            debug=os.environ.get("FLASK_DEBUG") == "1")
```

3. `templates/raio_x.html`: campo da comanda acima do peso:

```html
<label class="campo" for="comanda">Comanda
  <span class="campo__unidade"><input id="comanda" name="comanda" inputmode="numeric" placeholder="123"></span>
</label>
```

4. `static/js/raio-x.js`, na função `analisar()`, depois de `form.append("peso_g", gramas);`:

```js
form.append("comanda", document.getElementById("comanda").value.trim());
```

5. `templates/base.html` e `index.html`: trocar `url_for('gerente_login')` por `url_for('painel.painel')`; apagar `gerente.html`, `gerente_login.html` e `mesas.html`.
6. `.gitignore`: acrescentar `dados/`.
7. Formulário (Google Forms), para ligar a nota ao tempo real e controlar o cashback:
   - acrescentar as perguntas **"Mesa"** e **"Número da comanda"** (o painel reconhece pelo texto);
   - em *⋮ → Obter link pré-preenchido*, preencher a mesa e gerar **um link (e um QR Code) por mesa**. O cliente não precisa digitar a mesa;
   - manter a planilha em *Compartilhar → Qualquer pessoa com o link: Leitor*.

   Se o formulário mudar de planilha, defina `PLANILHA_AVALIACOES` com o novo link.
8. Menu do app: o link "Mesas" passa a abrir a tela do garçom (redirecionamento do passo 2).
