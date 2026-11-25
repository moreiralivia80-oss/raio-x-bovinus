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

Sem chave, o sistema funciona em **modo demonstração** (resultado de exemplo). Para analisar fotos de verdade:

1. Crie uma chave gratuita no [Google AI Studio](https://aistudio.google.com/apikey).
2. Defina a variável de ambiente antes de rodar:

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

## Estrutura

```
├── app.py                 # servidor Flask e rotas
├── servicos/
│   ├── gemini.py          # análise da foto com a IA
│   └── custos.py          # custo dos itens, custo e margem do prato
├── templates/             # páginas HTML (base.html tem o menu)
├── static/
│   ├── css/style.css      # identidade visual da Bovinu'S
│   └── js/                # menu e câmera do Raio-X
└── requirements.txt
```
