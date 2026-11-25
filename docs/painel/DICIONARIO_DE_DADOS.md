# Dicionário de dados

Banco: SQLite. No .exe fica em `executavel\dados\bovinus.db`; pelo Python, em `dados\bovinus.db`; outro caminho pela variável `BOVINUS_DB`. Definição completa em [`painel/schema.sql`](../painel/schema.sql).
Datas: texto `AAAA-MM-DD HH:MM:SS`, horário local. Valores em R$ e gramas.

Um banco criado por uma versão anterior do painel ganha as colunas novas sozinho ao abrir, sem perder dados.

## Como o sistema da casa consome

| Forma | Como |
|---|---|
| CSV (Excel) | `GET /api/painel/exportar/<nome>.csv` (com login): separador `;`, decimal `,`, UTF-8 com BOM. Texto que começa com `=`, `+`, `-` ou `@` sai com `'` na frente, para o Excel não executar como fórmula (comentário de cliente). |
| JSON | `GET /api/painel/dados?dias=7` (com login): tudo que o painel mostra. `&reais=1` limita a Dor 4 às respostas da planilha. |
| Direto no banco | qualquer ferramenta com driver SQLite (Power BI, DBeaver, Python) lendo as views `vw_*` |

Nomes exportáveis: `vw_jornada_cliente`, `vw_tempo_mesa_suja`, `vw_pratos`, `vw_mix_itens`, `vw_opiniao_itens`, `comandas`, `eventos_comanda`, `pratos`, `itens_prato`, `limpezas_mesa`, `avaliacoes`, `avaliacao_itens`, `mesas`, `itens_buffet`.

## Tabelas

### `mesas`
| Coluna | Tipo | Descrição |
|---|---|---|
| numero | inteiro, PK | número da mesa (cadastro inicial: Inferior 1-20, Principal 21-50, Superior 51-90) |
| salao | texto | `Inferior`, `Principal` ou `Superior` |
| lugares | inteiro | lugares (padrão 4) |

### `itens_buffet`
| Coluna | Tipo | Descrição |
|---|---|---|
| nome | texto, PK | nome do item, igual ao usado pelo Raio-X |
| categoria | texto | carne, acompanhamento, salada, quente, sobremesa, outro |
| custo_kg | real | custo em R$ por kg (valores iniciais **fictícios**, os mesmos de `servicos/custos.py`) |
| ativo | 0/1 | item no buffet hoje |

### `comandas`: um uso do cartão
| Coluna | Tipo | Descrição |
|---|---|---|
| id | inteiro, PK | identificador do uso |
| codigo | texto | número impresso / código de barras do cartão (reutilizado a cada cliente) |
| aberta_em | data | 1º pip |
| fechada_em | data | pip de pagamento (vazio = cliente ainda no salão) |
| mesa_numero | inteiro | mesa informada pelo garçom |

### `eventos_comanda`: cada pip
| Coluna | Tipo | Descrição |
|---|---|---|
| comanda_id | inteiro | uso da comanda |
| tipo | texto | `entrada`, `balanca`, `atendimento_mesa`, `pagamento` |
| momento | data | hora da leitura (do servidor; se guardada sem conexão, a hora do toque no aparelho) |
| mesa_numero | inteiro | obrigatório no `atendimento_mesa` |
| ponto | texto | onde foi lido (ex.: `Caixa 1`, `Balança`) |
| id_cliente | texto, único | identificador do toque gerado pelo aparelho; o reenvio da fila offline não duplica |

### `pratos`: um prato pesado
| Coluna | Tipo | Descrição |
|---|---|---|
| comanda_id | inteiro | comanda pipada na balança (pode ser vazio) |
| pesado_em | data | hora da pesagem |
| peso_g | real | peso do prato |
| receita | real | valor cobrado |
| custo_estimado | real | soma do custo dos itens |
| precisao | inteiro | 0 a 100, confiança da IA |
| origem | texto | `ia` ou `demonstracao` |

### `itens_prato`
| Coluna | Tipo | Descrição |
|---|---|---|
| prato_id | inteiro | prato |
| item, categoria | texto | item identificado |
| percentual | real | % do peso do prato |
| peso_g, custo | real | peso e custo estimados do item (custo do dia da pesagem) |
| confianca | inteiro | 0 a 100 |

### `limpezas_mesa`: ciclo suja → limpa
| Coluna | Tipo | Descrição |
|---|---|---|
| mesa_numero | inteiro | mesa |
| saiu_em | data | cliente saiu |
| limpa_em | data | mesa limpa (vazio = ainda suja) |
| origem | texto | quem marcou **suja**: `caixa` (última comanda da mesa pagou) ou `garcom` (toque) |
| limpa_origem | texto | quem marcou **limpa**: `garcom` (toque) ou `novo_cliente` (garçom atendeu a mesa sem ter tocado "limpa"; fica fora das médias) |

### `avaliacoes`: uma resposta da pesquisa
| Coluna | Tipo | Descrição |
|---|---|---|
| criada_em | data | hora da resposta (carimbo do Google Forms) |
| mesa_numero | inteiro | mesa, se o formulário perguntar (mesa inexistente é ignorada e a resposta é gravada) |
| comanda_id | inteiro | liga a nota ao tempo medido, se o formulário perguntar a comanda |
| nota_comida, nota_espera, nota_limpeza | 1 a 5 | perguntas 1, 2 e 3 do formulário (`5 - Excelente` → 5) |
| motivo | texto | pergunta 6, "O que não estava bom nesses itens?" (só quando algum item foi criticado) |
| comentario | texto | pergunta 7 (até 500 caracteres) |
| tema | texto | assunto do comentário: comida, espera, limpeza, atendimento, outro |
| beneficio | texto | `desconto` ou `cashback`, se o formulário registrar |
| origem | texto | `planilha` (Google Forms), `api` ou `simulado` |
| chave_origem | texto, único | impressão digital do carimbo da planilha: a mesma resposta nunca é importada 2 vezes |

### `avaliacao_itens`
| Coluna | Tipo | Descrição |
|---|---|---|
| avaliacao_id | inteiro | resposta |
| item | texto | nome do item, sem a categoria do formulário (`Churrasco: Picanha` → `Picanha`), com o nome do cadastro quando existe |
| opiniao | texto | `gostou` (pergunta 4) ou `nao_gostou` (pergunta 5) |

### `meta`
Chave e valor de configuração: `dados_simulados = 1` mostra a faixa de demonstração; `simulado_em` guarda quando a demonstração foi gerada.

## Views (prontas para relatório)

| View | Uma linha por | Colunas principais |
|---|---|---|
| `vw_jornada_cliente` | comanda | entrada, primeira_balanca, atendido_mesa, pagamento, qtd_pesagens, hora_entrada, **min_ate_pesar**, **min_ate_atendimento_mesa**, **min_permanencia**, mesa, salão |
| `vw_tempo_mesa_suja` | ciclo de limpeza | mesa, salão, saiu_em, limpa_em, origem, limpa_origem, hora, **min_suja**, **conta_na_media** (1 = garçom tocou "limpa" e durou até 90 min) |
| `vw_pratos` | prato | colunas de `pratos` + hora, lucro_bruto, **margem**, custo_por_kg |
| `vw_mix_itens` | item de prato | item, categoria, pesado_em, peso_g, custo, percentual, prato_id |
| `vw_opiniao_itens` | item avaliado | criada_em, mesa, origem, item, opiniao, motivo |

## API

### Gravação

| Método e rota | Corpo (JSON ou formulário) | Resposta |
|---|---|---|
| `POST /api/comanda/pipar` | `codigo`, `tipo`, `mesa` (obrigatória para `atendimento_mesa`), `ponto`, `id_cliente` (opcional), `momento` (opcional) | 201 com comanda, minutos desde a entrada e mesa marcada suja; **200 com `repetida: true`** se for a mesma leitura (mesmo `id_cliente`, ou mesma comanda e ponto em até 60 s) |
| `POST /api/mesas/<n>/saiu` | `momento` (opcional) | ciclo aberto (toque repetido não duplica) |
| `POST /api/mesas/<n>/limpa` | `momento` (opcional) | minutos que a mesa ficou suja |
| `POST /api/mesas/<n>/desfazer` | — | desfaz o último toque do garçom nessa mesa, até 2 min depois |
| `POST /api/pratos` | resultado do Raio-X + `codigo_comanda` | id do prato |
| `POST /api/avaliacoes` | `mesa`, `codigo_comanda`, `nota_comida`, `nota_espera`, `nota_limpeza`, `gostou`, `nao_gostou`, `motivo`, `comentario`, `beneficio` | id da avaliação (`origem = 'api'`) |
| `POST /api/painel/sincronizar` | — (com login) | lê a planilha agora: respostas novas, erros e hora |

Erros de validação (mesa inexistente, nota fora de 1 a 5, tipo inválido, data inválida) voltam com **400** e a mensagem em `erro`.

### Leitura

| Método e rota | Resposta |
|---|---|
| `GET /api/mesas` | situação de cada mesa agora: `livre`, `ocupada` (comanda aberta ligada a ela nas últimas 6 h) ou `suja` com os minutos |
| `GET /api/painel/dados?dias=1\|7\|30&reais=1` | todo o painel em JSON (com login) |
| `GET /api/painel/exportar/<nome>.csv` | tabela ou view em CSV (com login) |

## Pesquisa do Google Forms

Automático: o painel lê a planilha a cada 2 minutos (variável `PLANILHA_AVALIACOES`; `desligado` para não ler). Manual, a partir de um CSV baixado ou de outro link:

```powershell
python -m painel.planilha respostas.csv
```

O comando mostra como cada pergunta foi reconhecida, quantas respostas entraram e quantas já estavam no banco.
