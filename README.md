# Raio-X Bovinu'S

Projeto desenvolvido para o **Hackathon Tech FMU 2026.2**, em parceria com o restaurante **Bovinu'S Grill & Beer - Augusta**.

## Equipe

- _[Integrante 1]_
- _[Integrante 2]_
- _[Integrante 3]_

## Sobre o projeto

Sistema para ajudar a Bovinu'S a entender melhor o que acontece no salão: o que é servido nos pratos, quanto tempo as mesas ficam sujas e o que os clientes acham da comida e do tempo de espera.

### Raio-X do Prato

A câmera fotografa o prato na balança e a IA do Google Gemini identifica cada alimento, estima quanto do prato ele ocupa e informa o **nível de certeza** de cada identificação e a **precisão geral** da análise. Com o peso do prato e o custo do kg de cada item, o sistema calcula o **custo estimado** e a **margem** do prato.

> Os custos por kg e o preço de venda em `servicos/custos.py` são **fictícios**, apenas para demonstração.

## Como executar

```bash
pip install -r requirements.txt
python app.py
```

Abra **http://localhost:5000** no navegador.

### Ativar a IA (Gemini)

Sem a chave, **nenhuma foto é analisada** e a página avisa "IA desligada". Para analisar fotos de verdade:

1. Crie uma chave gratuita no [Google AI Studio](https://aistudio.google.com/apikey).
2. Rode `python app.py` uma vez. O arquivo **`.env`** aparece sozinho na pasta do projeto.
3. Abra o `.env`, cole a chave depois do `=` e salve:

```
GEMINI_API_KEY=sua-chave-aqui
```

4. Rode `python app.py` de novo. O terminal deve mostrar **IA ligada (Gemini)**.

O `.env` fica só no seu computador e não vai para o GitHub. Se preferir, também dá para definir a variável no terminal:

```powershell
# Windows (PowerShell)
$env:GEMINI_API_KEY="sua-chave-aqui"
python app.py
```

```bash
# Linux / Mac
export GEMINI_API_KEY="sua-chave-aqui"
python app.py
```

Nunca coloque a chave no código nem envie para o GitHub.

### Testar no celular

1. Computador e celular na **mesma rede Wi-Fi**.
2. Rode `python app.py` e veja o endereço que aparece no terminal (ex.: `http://192.168.0.10:5000`).
3. No celular, abra `http://SEU-IP:5000/raio-x`.
4. Toque em **Tirar foto**: a câmera do celular abre.

No computador (`localhost`), a câmera aparece ao vivo na própria página.

## Painel do gerente

Pelo menu **Área do gerente** (ou `http://localhost:5000/painel`). Login de demonstração: **gerente / bovinus2026** (troque com `PAINEL_USUARIO` e `PAINEL_SENHA` no `.env`).

- **Pratos registrados pelo Raio-X:** cada prato analisado pela IA fica salvo com a **foto** e as **comidas** (em `dados/`, fora do GitHub). O painel mostra os **produtos mais consumidos**, o peso e o custo médio, a precisão média da IA e os últimos pratos com foto.
- **Mix do prato, fila, limpeza das mesas e avaliações** (Google Forms, sincronizado a cada 2 minutos), com alertas automáticos.
- Os toques na tela **Mesas** também alimentam a seção de limpeza do painel.

Para apresentar com o painel cheio, gere 30 dias de dados de demonstração (uma vez):

```bash
python -m painel.simulador
```

Detalhes do painel em [`docs/painel/`](docs/painel/DOCUMENTACAO.md). Testes do painel: `python -m unittest discover testes`.

## Estrutura

```
├── app.py                 # servidor Flask e rotas
├── servicos/
│   ├── gemini.py          # análise da foto com a IA
│   ├── custos.py          # custo dos itens, custo e margem do prato
│   └── mesas.py           # tela de mesas (garçom)
├── painel/                # painel do gerente (login, gráficos, Google Forms, pratos registrados)
├── testes/                # testes do painel
├── docs/painel/           # documentação do painel
├── templates/             # páginas HTML (base.html tem o menu)
├── static/
│   ├── css/style.css      # identidade visual da Bovinu'S
│   └── js/                # menu e câmera do Raio-X
└── requirements.txt
```

## Problemas comuns

- **A IA não responde, demora ou dá erro:** rode `python diagnostico_ia.py` na pasta do projeto. Ele testa a conexão e a chave direto com o Google e mostra qual modelo responde e em quanto tempo.

- **Depois do Pull a página continua igual:** pare o servidor (Ctrl + C), rode `python app.py` de novo e atualize o navegador com **Ctrl + F5**.
- **A câmera não aparece ao vivo no computador:** abra por `http://localhost:5000/raio-x`. Pelo endereço de rede (`http://192.168...`), o navegador bloqueia a câmera ao vivo; use **Enviar foto**.
- **Aparece "IA desligada":** a chave do Gemini não foi configurada no terminal onde o servidor está rodando. Defina `GEMINI_API_KEY` e rode `python app.py` de novo.

### Modo demonstração (opcional)

Para ensaiar a apresentação sem internet, rode com `RAIOX_DEMO=1` (PowerShell: `$env:RAIOX_DEMO="1"`). Nesse modo os resultados são **exemplos** e a foto não é analisada; a página avisa isso.
