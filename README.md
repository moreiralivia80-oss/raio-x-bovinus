# Raio-X Bovinu'S

> **Hackathon Tech FMU 2026.2 · Desafio Bovinu'S Grill & Beer - Augusta**
> Equipe: _[nome da equipe]_ · _[Integrante 1]_, _[Integrante 2]_, _[Integrante 3]_

**A Bovinu'S sabe o peso de cada prato e o total do caixa, mas não sabe o que foi servido, quanto tempo as mesas ficam sujas nem o que o cliente achou.**
O Raio-X Bovinu'S coleta esses dados sem dar trabalho para a equipe e mostra tudo em um painel para o gerente.

**Vídeo demonstrativo (até 2 min):** _[link]_
**Apresentação (5 slides):** [`docs/apresentacao.pdf`](docs/apresentacao.pdf)

---

## 1. O problema

Dores apresentadas pela Bovinu'S na abertura do hackathon (24/11/2026):

| Dor apresentada pelo restaurante | Módulo que resolve |
|---|---|
| **"Mix" do prato:** sabem o peso, mas não o que foi servido. Ingredientes mais caros afetam o lucro. | 1. Raio-X do Prato |
| **Limpeza do salão:** quanto tempo as mesas ficam sujas após o cliente sair? | 3. Controle das mesas |
| **Qualidade da comida:** o que o cliente acha? Quais comidas não agradam? | 2. Avaliação do cliente |
| **Filas e tempo do cliente** | 2. Avaliação (nota do tempo de espera por horário) |

Modelo da casa: **self-service por peso**. O cliente se serve, pesa o prato e escolhe a mesa. Os garçons servem bebidas e limpam as mesas.

## 2. A solução

### Módulo 1: Raio-X do Prato
Uma câmera na balança fotografa o prato. A IA (Google Gemini) estima a porcentagem de cada item do buffet, e o sistema calcula, com pandas: `peso × % do item × custo do kg` → **custo estimado e margem de cada prato**.

### Módulo 2: Avaliação do cliente
QR Code na mesa, como um cardápio: *"Ao final da refeição, se puder, avalie sua experiência. A Bovinu'S agradece!"*
O cliente responde com poucos toques: nota da comida, nota do tempo de espera, **item de que mais gostou**, **item que não estava bom** e um comentário opcional. A IA classifica o assunto do comentário (comida, espera, limpeza, atendimento).

### Módulo 3: Controle das mesas
Mapa das ~90 mesas (salões inferior, principal e superior). O garçom toca na mesa quando o cliente sai (fica vermelha) e toca de novo quando ela está limpa. O sistema calcula o **tempo de mesa suja** e mostra as mesas sujas há mais de 5 minutos.

### Módulo 4: Painel do gerente
Custo médio por prato, margem, mix por categoria (% do peso × % do custo), itens que mais pesam no custo, itens mais elogiados e criticados, notas por horário e tempo de mesa suja por salão e horário.

### Recomendações que os dados permitem
O sistema **mede**, e o gerente **decide**. Exemplos de decisões que o painel apoia:
- Nos horários em que a nota do tempo de espera cai, reforçar a equipe na churrasqueira ou dividir as filas.
- No salão com maior tempo de mesa suja, remanejar um garçom no pico.
- Rever receita ou reposição dos itens mais criticados.

## 3. Capturas de tela

_(máximo 5, em `assets/prints/`)_

## 4. Arquitetura

```
[Câmera na balança]   [QR Code na mesa]   [Celular do garçom]
        │                     │                    │
        ▼                     ▼                    ▼
  Raio-X do Prato         Avaliação             Mesas         ← telas em Streamlit
        │                     │                    │
        └──────► core/ia.py (Gemini) ◄──────┘
                         │
                 core/calculos.py (pandas)
                         │
                 SQLite (data/bovinus.db)
                         │
                         ▼
                 Painel do gerente
```

### Banco de dados
| Tabela | Conteúdo |
|---|---|
| `itens` | itens do buffet, categoria e custo por kg |
| `config` | preço de venda do kg |
| `pratos` / `prato_itens` | cada pesagem e sua composição estimada |
| `avaliacoes` / `avaliacao_itens` | notas, comentário, assunto e itens elogiados/criticados |
| `mesa_eventos` | "cliente saiu" e "limpa" de cada mesa, com horário |

Script das tabelas: [`core/db.py`](core/db.py). Diagramas em [`docs/diagramas/`](docs/diagramas/).

## 5. Decisões técnicas

| Tecnologia | Por quê |
|---|---|
| **Python + pandas** | Linguagem que toda a equipe domina; pandas faz os cálculos e agrupamentos |
| **Streamlit** | Cria as telas web direto em Python, sem precisar de front-end separado |
| **SQLite** | Banco em um único arquivo, sem instalação |
| **Google Gemini (API)** | Reconhece alimentos na foto e classifica comentários sem treinar modelo próprio. Sem chave, o sistema roda em **modo demo** |
| **Streamlit Community Cloud** | Hospedagem gratuita ligada ao GitHub, para o QR Code abrir em qualquer celular |

Privacidade (LGPD): a câmera enquadra **apenas o prato**; a avaliação é anônima.

## 6. Como executar

```bash
git clone <url-do-repositorio>
cd raio-x-bovinus
python -m venv .venv
# Windows: .venv\Scripts\activate   |   Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Na primeira execução, o banco é criado automaticamente com dados de demonstração.
Para recriar do zero: `python -m core.seed`

**Para usar a IA real:** copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e coloque sua chave do Google AI Studio.

**Link do QR Code de cada mesa:** `<url-do-app>/Avaliacao?mesa=12`

> Custos por kg, preço de venda e histórico simulado são **fictícios**, apenas para demonstração.

## 7. Próximos passos

- Integração com a balança e o PDV existentes (peso automático)
- Foto do prato devolvido para medir sobras
- Alerta de reposição das cubas a partir do consumo por item

## 8. Estrutura do repositório

```
├── app.py                  # página inicial
├── pages/                  # as 4 telas (balança, avaliação, mesas, painel)
├── core/                   # banco, cálculos (pandas), IA e dados de exemplo
├── data/                   # banco SQLite (gerado automaticamente)
├── assets/prints/          # capturas de tela (até 5)
├── docs/                   # slides e diagramas
└── requirements.txt
```
