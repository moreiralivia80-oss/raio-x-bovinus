"""Custo dos itens do buffet e cálculo de custo e margem do prato.

ATENÇÃO: os valores abaixo são FICTÍCIOS, apenas para demonstração.
Troque pelos custos reais quando a Bovinu'S fornecer.
"""
import unicodedata

PRECO_KG_VENDA = 89.90  # R$ por kg cobrado do cliente (FICTÍCIO)

# nome do item: (categoria, custo em R$ por kg)
ITENS = {
    "Picanha": ("carne", 75.0),
    "Fraldinha": ("carne", 48.0),
    "Costela": ("carne", 38.0),
    "Cupim": ("carne", 42.0),
    "Maminha": ("carne", 45.0),
    "Linguiça": ("carne", 24.0),
    "Frango": ("carne", 18.0),
    "Coração de frango": ("carne", 22.0),
    "Peixe": ("carne", 40.0),
    "Arroz": ("acompanhamento", 6.0),
    "Feijão": ("acompanhamento", 8.0),
    "Farofa": ("acompanhamento", 9.0),
    "Batata frita": ("acompanhamento", 14.0),
    "Mandioca": ("acompanhamento", 7.0),
    "Macarrão": ("acompanhamento", 8.0),
    "Salada verde": ("salada", 10.0),
    "Tomate": ("salada", 8.0),
    "Vinagrete": ("salada", 9.0),
    "Maionese": ("salada", 12.0),
    "Legumes": ("salada", 9.0),
    "Estrogonofe": ("quente", 22.0),
    "Lasanha": ("quente", 20.0),
    "Pudim": ("sobremesa", 16.0),
    "Mousse": ("sobremesa", 14.0),
}

# custo usado quando a IA encontra um item que não está na lista
CUSTO_PADRAO_CATEGORIA = {
    "carne": 40.0, "acompanhamento": 8.0, "salada": 10.0,
    "quente": 20.0, "sobremesa": 15.0, "outro": 12.0,
}


def _chave(texto):
    sem_acento = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return sem_acento.lower().strip()


_INDICE = {_chave(nome): nome for nome in ITENS}


def nomes_itens():
    return list(ITENS)


def localizar_item(nome, categoria_ia="outro"):
    """Devolve (nome_padronizado, categoria, custo_kg, conhecido)."""
    chave = _chave(nome)
    nome_ok = _INDICE.get(chave)
    if not nome_ok:  # ex.: "Arroz branco" -> "Arroz", "Salada de alface" não casa com nada
        for conhecido in sorted(_INDICE, key=len, reverse=True):
            if chave.startswith(conhecido + " ") or chave.endswith(" " + conhecido):
                nome_ok = _INDICE[conhecido]
                break
    if nome_ok:
        categoria, custo = ITENS[nome_ok]
        return nome_ok, categoria, custo, True
    categoria = categoria_ia if categoria_ia in CUSTO_PADRAO_CATEGORIA else "outro"
    return nome.strip().capitalize(), categoria, CUSTO_PADRAO_CATEGORIA[categoria], False


def calcular(peso_g, analise):
    """Junta a análise da IA com o peso e os custos. Devolve o resultado para a tela."""
    itens_ia = [i for i in analise.get("itens", []) if float(i.get("percentual", 0)) > 0]
    total_pct = sum(float(i["percentual"]) for i in itens_ia) or 1

    itens, custo_total = [], 0.0
    for i in itens_ia:
        nome, categoria, custo_kg, conhecido = localizar_item(i.get("nome", "Item"), i.get("categoria", "outro"))
        percentual = float(i["percentual"]) * 100 / total_pct   # normaliza para somar 100%
        peso_item = peso_g * percentual / 100
        custo = peso_item / 1000 * custo_kg
        custo_total += custo
        itens.append({
            "nome": nome,
            "categoria": categoria,
            "percentual": round(percentual, 1),
            "peso_g": round(peso_item),
            "custo": round(custo, 2),
            "confianca": int(max(0, min(100, float(i.get("confianca", 0))))),
            "custo_conhecido": conhecido,
        })

    itens.sort(key=lambda x: x["percentual"], reverse=True)
    receita = peso_g / 1000 * PRECO_KG_VENDA
    return {
        "peso_g": peso_g,
        "receita": round(receita, 2),
        "custo_estimado": round(custo_total, 2),
        "margem": round((receita - custo_total) / receita, 4) if receita and itens else None,
        "itens": itens,
        "precisao": int(max(0, min(100, float(analise.get("confianca_geral", 0))))),
        "observacao": analise.get("observacao", ""),
        "e_prato_de_comida": analise.get("e_prato_de_comida", True),
    }
