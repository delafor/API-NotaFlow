import hashlib
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

from extractor import validar_gtin_ean


# Dicionário de expansão de abreviações fiscais comuns em NFC-e de supermercados
EXPANSOES_ABREVIACOES: Dict[str, str] = {
    "ARR": "ARROZ",
    "ARZ": "ARROZ",
    "FEIJ": "FEIJAO",
    "FJ": "FEIJAO",
    "ACUC": "ACUCAR",
    "ACUC.": "ACUCAR",
    "CAF": "CAFE",
    "LEIT": "LEITE",
    "LT": "LEITE",
    "OL": "OLEO",
    "MAC": "MACARRAO",
    "REFRIG": "REFRIGERANTE",
    "REFR": "REFRIGERANTE",
    "SAB": "SABAO",
    "DETERG": "DETERGENTE",
    "DET": "DETERGENTE",
    "DESINF": "DESINFETANTE",
    "AMAC": "AMACIANTE",
    "MARG": "MARGARINA",
    "MANT": "MANTEIGA",
    "BISC": "BISCOITO",
    "BOL": "BISCOITO",
    "CHOC": "CHOCOLATE",
    "FAR": "FARINHA",
    "FRG": "FRANGO",
    "BOV": "BOVINA",
    "SUIN": "SUINA",
    "PAP": "PAPEL",
    "HIG": "HIGIENICO",
    "CR": "CREME",
    "DENT": "DENTAL",
    "SABON": "SABONETE",
    "SHAMP": "SHAMPOO",
    "COND": "CONDICIONADOR",
    "CERV": "CERVEJA",
    "AG": "AGUA",
    "MIN": "MINeral",
    "TRAD": "TRADICIONAL",
    "INT": "INTEGRAL",
    "DESN": "DESNATADO",
    "SEMIDESN": "SEMIDESNATADO",
    "PARB": "PARBOILIZADO",
    "TP1": "TIPO 1",
    "TP2": "TIPO 2",
    "T1": "TIPO 1",
    "T2": "TIPO 2",
    "PCT": "PACOTE",
    "CX": "CAIXA",
    "GF": "GARRAFA",
    "GARR": "GARRAFA",
    "BDJ": "BANDEJA",
}

# Vocabulário determinístico de marcas conhecidas do varejo brasileiro
MARCAS_CONHECIDAS = {
    "CAMIL", "TIO JOAO", "PRATO FINO", "NAMORADO", "BROTO LEGAL", "KICALDO", "URBANO",
    "TURQUESA", "COMBRASIL", " DONA BENTA", "DONA BENTA", "SOL", "RENATA", "ADRIA",
    "BARILLA", "BAUDUCCO", "VITARELLA", "MARILAN", "NESTLE", "GAROTO", "LACTA",
    "ITAMBE", "PIRACANJUBA", "PARMALAT", "ELEGÊ", "ELEGE", "ITALAC", "TIROL",
    "NINHO", "MOLICO", "DANONE", "VIGOR", "BATAVO", "PRESIDENT", "QUALY", "DORIANA",
    "CLAYBOM", "DELICIA", "SOYA", "LIZA", "CONCORDIA", "SINHA", "GALLO", "ANDORINHA",
    "BORGES", "COCINERO", "PILAO", "MELITTA", "TRES CORACOES", "3 CORACOES", "CABOCLO",
    "SANTA CLARA", "MARATA", " IGUAÇU", "IGUACU", "NESCAFE", "UNIAO", "DA BARRA",
    "CARAVELAS", "GUARANI", "COCA COLA", "COCA-COLA", "PEPSI", "GUARANA ANTARCTICA",
    "ANTARCTICA", "FANTA", "SPRITE", "KUAT", "SCHWEPPES", "HEINEKEN", "BRAHMA",
    "SKOL", "AMSTEL", "BUDWEISER", "STELLA ARTOIS", "SPATEN", "ITAIPAVA", "EISENBAHN",
    "SADIA", "PERDIGAO", "SEARA", "AURORA", "FRIBOI", "SWIFT", "MINERVA",
    "YPE", "OMO", "BRILHANTE", "TIXAN", "ARIEL", "DOWNY", "COMFORT", "FOFO",
    "VEJA", "PINHO SOL", "LYSOFORM", "BOMBRIL", "ASSOLAN", "LIMPOL", "MINUANO",
    "COLGATE", "SORRISO", "ORAL B", "ORAL-B", "CLOSE UP", "CLOSEUP", "SENSODYNE",
    "DOVE", "LUX", "REXONA", "NIVEA", "PROTEX", "PALMOLIVE", "PHEBO", "SEDA",
    "PANTENE", "ELSEVE", "CLEAR", "NEVE", "PERSONAL", "SUBLIME", "DUETTO", "MILI",
    "HELLMANNS", "HEINZ", "QUERO", "POMAROLA", "ELEFANTE", "FUGINI", "PREDILECTA",
    "MAGGI", "KNORR", "SAZON", "KITANO", " TANG", "TANG", "CLIGHT", "TODDY", "NESCAU",
    "ALIANCA", "TRAMONTINA", "TIGRE", "LORENZETTI",
}

# Variantes e tipos mutuamente exclusivos que NUNCA podem ser misturados
QUALIFICADORES_TIPO = [
    ("TIPO 1", ["TIPO 1", "TP 1", "T1", "TIPO1"]),
    ("TIPO 2", ["TIPO 2", "TP 2", "T2", "TIPO2"]),
    ("PARBOILIZADO", ["PARBOILIZADO", "PARB"]),
    ("ARBÓRIO", ["ARBORIO"]),
    ("INTEGRAL", ["INTEGRAL", "INT."]),
    ("DESNATADO", ["DESNATADO", "DESN"]),
    ("SEMIDESNATADO", ["SEMIDESNATADO", "SEMI DESNATADO", "SEMI-DESNATADO"]),
    ("ZERO LACTOSE", ["ZERO LACTOSE", "SEM LACTOSE", "NOLAC", "0 LACTOSE"]),
    ("ZERO ACUCAR", ["ZERO ACUCAR", "SEM ACUCAR", "DIET", "ZERO"]),
    ("TRADICIONAL", ["TRADICIONAL", "TRAD"]),
    ("EXTRAFORTE", ["EXTRAFORTE", "EXTRA FORTE", "FORTE"]),
    ("DESCAFEINADO", ["DESCAFEINADO"]),
    ("REFINADO", ["REFINADO"]),
    ("CRISTAL", ["CRISTAL"]),
    ("DEMERARA", ["DEMERARA"]),
    ("MASCAVO", ["MASCAVO"]),
    ("CARIOQUINHA", ["CARIOCA", "CARIOQUINHA"]),
    ("PRETO", ["PRETO"]),
    ("FRADINHO", ["FRADINHO", "MACASSAR"]),
    ("BRANCO", ["BRANCO"]),
    ("VERMELHO", ["VERMELHO"]),
]

EMBALAGENS_CONHECIDAS = [
    ("CAIXA", ["CAIXA", "CX", "TP", "TETRA PAK"]),
    ("PACOTE", ["PACOTE", "PCT", "SACO"]),
    ("GARRAFA", ["GARRAFA", "GF", "PET", "VIDRO"]),
    ("LATA", ["LATA", "LT"]),
    ("SACHE", ["SACHE", "REFIL"]),
    ("BANDEJA", ["BANDEJA", "BDJ"]),
    ("FARDO", ["FARDO", "FD"]),
]

CATEGORIAS_PALAVRAS = {
    "mercearia_graos": ["ARROZ", "FEIJAO", "LENTILHA", "GRAO DE BICO", "MILHO", "FARINHA", "FUBA", "AVEIA", "MACARRAO", "MASSA"],
    "mercearia_basicos": ["ACUCAR", "SAL", "OLEO", "AZEITE", "VINAGRE", "CAFE", "ACHOCOLATADO", "MOLHO", "EXTRATO", "MAIONESE", "KETCHUP"],
    "laticinios": ["LEITE", "QUEIJO", "MANTEIGA", "MARGARINA", "IOGURTE", "REQUEIJAO", "CREME DE LEITE", "LEITE CONDENSADO"],
    "carnes_proteinas": ["CARNE", "BOVINA", "PATINHO", "ACEM", "ALCATRA", "PICANHA", "COSTELA", "FRANGO", "PEITO DE FRANGO", "COXA", "SUINA", "LINGUICA", "SALSICHA", "OVO", "OVOS", "PEIXE", "TILAPIA"],
    "bebidas": ["REFRIGERANTE", "SUCO", "AGUA", "CERVEJA", "VINHO", "ENERGETICO", "CHA"],
    "padaria_biscoitos": ["PAO", "BISCOITO", "BOLACHA", "TORRADA", "BOLO", "CHOCOLATE", "BOMBOM"],
    "limpeza": ["SABAO", "DETERGENTE", "AMACIANTE", "AGUA SANITARIA", "DESINFETANTE", "LIMPADOR", "ESPONJA", "LA DE ACO", "ALCOOL"],
    "higiene_pessoal": ["SABONETE", "SHAMPOO", "CONDICIONADOR", "CREME DENTAL", "PASTA DE DENTE", "DESODORANTE", "PAPEL HIGIENICO", "ABSORVENTE", "FRALDA"],
    "hortifruti": ["TOMATE", "CEBOLA", "BATATA", "ALHO", "CENOURA", "BANANA", "MACA", "LARANJA", "LIMAO", "ALFACE", "MAMAO"],
    "utilidades_construcao": ["MANGUEIRA", "REGULADOR", "ABRACADEIRA", "LAMPADA", "PILHA", "FITA", "TUBO", "CONEXAO"],
    "transporte_passagens": ["PASSAGEM", "BILHETE", "VIAGEM"],
}

STOPWORDS_PRODUTO = {
    "DE", "DA", "DO", "DAS", "DOS", "COM", "PARA", "POR", "EM", "UN", "UND", "UNID",
    "PC", "PCA", "X", "C", "S",
}


def remover_acentos(texto: str) -> str:
    if not texto:
        return ""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _extrair_medida_do_nome(texto_upper: str, unidade_item: str = "UN") -> Tuple[float, str, str, float, str]:
    """
    Extrai peso, volume ou quantidade da descrição do produto.
    Retorna: (quantidade_embalagem, unidade_medida, unidade_padrao, fator_para_padrao, texto_sem_medida)
    Ex:
      "ARROZ TIPO 1 CAMIL 5KG" -> (5.0, "KG", "KG", 5.0, "ARROZ TIPO 1 CAMIL")
      "CAFE PILAO 500G" -> (500.0, "G", "KG", 0.5, "CAFE PILAO")
      "OLEO SOYA 900ML" -> (900.0, "ML", "L", 0.9, "OLEO SOYA")
      "REFRIGERANTE COCA COLA 2L" -> (2.0, "L", "L", 2.0, "REFRIGERANTE COCA COLA")
    """
    un_item_clean = (unidade_item or "UN").strip().upper()
    if un_item_clean in ("KG", "KILO", "QUILO", "KG."):
        # Produto vendido a granel no peso (ex: Carne Bovina KG)
        # Mas verifica se tem peso fixo explícito no nome (ex: "ARROZ 5KG" registrado com UN: KG ou UN)
        match_fixo = re.search(r"\b(\d+(?:[.,]\d+)?)\s*(KG|QUILOS?|G|GR|GRAMAS?|L|LT|LITROS?|ML)\b", texto_upper)
        if not match_fixo:
            return 1.0, "KG", "KG", 1.0, texto_upper

    # Regex para capturar medida na descrição: 5KG, 5 KG, 500G, 500 GR, 900ML, 1,5L, 2 L, 12UN
    padrao_medida = re.compile(
        r"\b(\d+(?:[.,]\d+)?)\s*(KG|KILOS?|QUILOS?|G|GR|GRAMAS?|MG|L|LT|LITROS?|ML|M|MT|METROS?|UN|UND|UNID|ROLOS?|FOLHAS?)\b",
        re.IGNORECASE,
    )

    matches = list(padrao_medida.finditer(texto_upper))
    if matches:
        # Prioriza o último match de medida (geralmente no final do nome do produto)
        ultimo = matches[-1]
        val_str = ultimo.group(1).replace(",", ".")
        un_raw = ultimo.group(2).upper()
        try:
            valor = float(val_str)
        except ValueError:
            valor = 1.0

        texto_limpo = (texto_upper[:ultimo.start()] + " " + texto_upper[ultimo.end():]).strip()
        texto_limpo = re.sub(r"\s+", " ", texto_limpo)

        if un_raw in ("KG", "KILO", "KILOS", "QUILO", "QUILOS"):
            return valor, "KG", "KG", valor, texto_limpo
        elif un_raw in ("G", "GR", "GRAMA", "GRAMAS"):
            # Se for ex: 500G -> 0.5 KG para cálculo de R$/KG
            return valor, "G", "KG", round(valor / 1000.0, 4), texto_limpo
        elif un_raw in ("L", "LT", "LITRO", "LITROS"):
            return valor, "L", "L", valor, texto_limpo
        elif un_raw == "ML":
            return valor, "ML", "L", round(valor / 1000.0, 4), texto_limpo
        elif un_raw in ("M", "MT", "METRO", "METROS"):
            return valor, "MT", "MT", valor, texto_limpo
        else:
            return valor, "UN", "UN", valor, texto_limpo

    # Caso não haja medida explícita no nome, usa a unidade da linha da nota
    if un_item_clean in ("KG", "KILO", "QUILO"):
        return 1.0, "KG", "KG", 1.0, texto_upper
    elif un_item_clean in ("L", "LT", "LITRO"):
        return 1.0, "L", "L", 1.0, texto_upper
    elif un_item_clean in ("M", "MT", "METRO"):
        return 1.0, "MT", "MT", 1.0, texto_upper

    return 1.0, "UN", "UN", 1.0, texto_upper


def _identificar_marca(texto_upper: str) -> Optional[str]:
    """Identifica marca comercial conhecida de forma determinística."""
    # Primeiro verifica marcas compostas (2+ palavras)
    for marca in sorted(MARCAS_CONHECIDAS, key=len, reverse=True):
        m_clean = marca.strip()
        if re.search(rf"\b{re.escape(m_clean)}\b", texto_upper):
            if m_clean == "3 CORACOES":
                return "TRES CORACOES"
            if m_clean == "COCA-COLA":
                return "COCA COLA"
            if m_clean == "ORAL-B":
                return "ORAL B"
            if m_clean == "CLOSEUP":
                return "CLOSE UP"
            return m_clean
    return None


def _identificar_tipos_produto(texto_upper: str) -> List[str]:
    """Identifica qualificadores críticos (ex: INTEGRAL vs DESNATADO, TIPO 1 vs PARBOILIZADO)."""
    encontrados = []
    for canonic, variantes in QUALIFICADORES_TIPO:
        for v in variantes:
            if re.search(rf"\b{re.escape(v)}\b", texto_upper):
                if canonic not in encontrados:
                    encontrados.append(canonic)
                break
    # Se tem SEMIDESNATADO, remove DESNATADO isolado para não confundir
    if "SEMIDESNATADO" in encontrados and "DESNATADO" in encontrados:
        encontrados.remove("DESNATADO")
    return encontrados


def _identificar_embalagem(texto_upper: str) -> Optional[str]:
    for canonic, variantes in EMBALAGENS_CONHECIDAS:
        for v in variantes:
            if re.search(rf"\b{re.escape(v)}\b", texto_upper):
                return canonic
    return None


def _identificar_categoria(texto_upper: str) -> str:
    for cat_id, palavras in CATEGORIAS_PALAVRAS.items():
        for p in palavras:
            if re.search(rf"\b{re.escape(p)}\b", texto_upper):
                return cat_id
    return "outros"


def normalizar_produto(
    nome_bruto: str,
    unidade_nota: str = "UN",
    codigo_nota: Optional[str] = None,
    gtin_extraido: Optional[str] = None,
    preco_praticado: float = 0.0,
) -> Dict:
    """
    Realiza a normalização determinística completa de um produto de nota fiscal.
    Garante que:
    - Arroz 5 kg != Arroz 1 kg
    - Leite integral != Leite desnatado
    - Café Marca A != Café Marca B na correspondência exata, mas permite agrupamento equivalente por categoria/tipo.
    """
    if not nome_bruto or not nome_bruto.strip():
        raise ValueError("Nome do produto não pode ser vazio para normalização.")

    raw = nome_bruto.strip()

    # 1. Verifica se há GTIN/EAN no prefixo ou nos parâmetros
    gtin = gtin_extraido if (gtin_extraido and validar_gtin_ean(gtin_extraido)) else None
    match_prefix_num = re.match(r"^\s*(\d+)\s*-\s*(.+)$", raw)
    if match_prefix_num:
        possivel_ean = match_prefix_num.group(1)
        if not gtin and validar_gtin_ean(possivel_ean):
            gtin = possivel_ean
        raw = match_prefix_num.group(2).strip()

    if not gtin and codigo_nota:
        cand = re.sub(r"\D", "", str(codigo_nota))
        if validar_gtin_ean(cand):
            gtin = cand

    # 2. Remove acentos e normaliza para UPPERCASE
    upper = remover_acentos(raw).upper()
    upper = re.sub(r"[^\w\s.,/-]", " ", upper)
    upper = re.sub(r"\s+", " ", upper).strip()

    # 3. Expande abreviações fiscais comuns token a token
    tokens_iniciais = upper.split()
    tokens_expandidos = []
    for tk in tokens_iniciais:
        tk_sem_ponto = tk.rstrip(".")
        if tk in EXPANSOES_ABREVIACOES:
            tokens_expandidos.append(EXPANSOES_ABREVIACOES[tk])
        elif tk_sem_ponto in EXPANSOES_ABREVIACOES:
            tokens_expandidos.append(EXPANSOES_ABREVIACOES[tk_sem_ponto])
        else:
            tokens_expandidos.append(tk)

    texto_expandido = " ".join(tokens_expandidos)

    # 4. Extrai peso / volume / quantidade da embalagem
    qtd_emb, un_medida, un_padrao, fator_padrao, texto_sem_medida = _extrair_medida_do_nome(
        texto_expandido, unidade_nota
    )

    # 5. Identifica Marca, Tipo/Qualificador, Embalagem e Categoria
    marca = _identificar_marca(texto_expandido)
    tipos = _identificar_tipos_produto(texto_expandido)
    embalagem = _identificar_embalagem(texto_expandido)
    categoria_id = _identificar_categoria(texto_expandido)

    # 6. Extrai o núcleo base do produto (removendo marca, medidas e stopwords)
    nucleo_texto = texto_sem_medida
    if marca:
        nucleo_texto = re.sub(rf"\b{re.escape(marca)}\b", " ", nucleo_texto)
    for _, vars_tipo in QUALIFICADORES_TIPO:
        for vt in vars_tipo:
            nucleo_texto = re.sub(rf"\b{re.escape(vt)}\b", " ", nucleo_texto)
    for _, vars_emb in EMBALAGENS_CONHECIDAS:
        for ve in vars_emb:
            nucleo_texto = re.sub(rf"\b{re.escape(ve)}\b", " ", nucleo_texto)

    palavras_nucleo = []
    for p in re.split(r"[\s/.-]+", nucleo_texto):
        p_clean = p.strip()
        if not p_clean or p_clean in STOPWORDS_PRODUTO:
            continue
        if p_clean.isdigit() and len(p_clean) >= 3:
            # Mantém códigos de modelo relevantes se for ferramenta/regulador (ex: 506)
            if categoria_id == "utilidades_construcao":
                palavras_nucleo.append(p_clean)
            continue
        if len(p_clean) >= 2:
            palavras_nucleo.append(p_clean)

    if not palavras_nucleo:
        palavras_nucleo = [t for t in texto_sem_medida.split() if len(t) >= 2][:3]

    item_base = " ".join(palavras_nucleo[:4])
    tipo_str = " ".join(tipos) if tipos else ""

    # Formata medida legível (ex: 5 kg, 500 g, 900 ml, 1 un)
    qtd_fmt = int(qtd_emb) if qtd_emb == int(qtd_emb) else qtd_emb
    medida_chave = f"{qtd_fmt}{un_medida.lower()}"
    medida_exibicao = f"{qtd_fmt} {un_medida.lower()}" if un_medida != "UN" or qtd_emb > 1 else "1 un"

    # 7. Constrói Nome de Exibição Padronizado e Nome Normalizado
    partes_exibicao = [item_base.title()]
    if tipo_str:
        partes_exibicao.append(tipo_str.title())
    if marca:
        partes_exibicao.append(f"Marca {marca.title()}")
    if un_medida != "UN" or qtd_emb > 1:
        partes_exibicao.append(medida_exibicao)

    nome_exibicao = " — ".join(partes_exibicao)

    partes_norm = [item_base]
    if tipo_str:
        partes_norm.append(tipo_str)
    if marca:
        partes_norm.append(marca)
    partes_norm.append(f"{qtd_fmt}{un_medida}")
    nome_normalizado = " ".join(partes_norm).strip()

    # 8. Gera Identificadores Estáveis (produto_id e chave_equivalente)
    # Chave de equivalência (mesmo produto base + mesmo tipo estrito + mesma unidade padrão, independente da marca)
    slug_base = re.sub(r"[^a-z0-9]+", "_", item_base.lower()).strip("_")
    slug_tipo = re.sub(r"[^a-z0-9]+", "_", tipo_str.lower()).strip("_") or "padrao"
    slug_marca = re.sub(r"[^a-z0-9]+", "_", (marca or "generico").lower()).strip("_")

    chave_equivalente = f"eq_{slug_base}_{slug_tipo}_{medida_chave}"
    chave_familia_unidade = f"fam_{slug_base}_{slug_tipo}_{un_padrao.lower()}"

    if gtin:
        produto_id = f"gtin_{gtin}"
    else:
        # Mesmo sem GTIN, separa rigorosamente por item_base + tipo + marca + medida_chave
        assinatura_exata = f"{slug_base}__{slug_tipo}__{slug_marca}__{medida_chave}"
        if len(assinatura_exata) <= 64:
            produto_id = f"prod_{assinatura_exata}"
        else:
            h = hashlib.sha256(assinatura_exata.encode("utf-8")).hexdigest()[:16]
            produto_id = f"prod_{slug_base[:20]}_{h}"

    # 9. Calcula preço por unidade padronizada (R$/KG, R$/L, R$/UN)
    preco_por_unidade = None
    if preco_praticado > 0 and fator_padrao > 0:
        preco_por_unidade = round(preco_praticado / fator_padrao, 2)

    # 10. Gera tokens de busca para indexação no Firestore (ARRAY_CONTAINS)
    tokens_set = set()
    for palavra in re.split(r"[\s—_-]+", f"{nome_normalizado} {gtin or ''} {categoria_id}".lower()):
        p_clean = remover_acentos(palavra).strip()
        if len(p_clean) >= 2 and p_clean.upper() not in STOPWORDS_PRODUTO:
            tokens_set.add(p_clean)
    # Adiciona também a combinação compacta da medida (ex: "5kg", "500g")
    tokens_set.add(medida_chave.lower())

    return {
        "produto_id": produto_id,
        "chave_equivalente": chave_equivalente,
        "chave_familia_unidade": chave_familia_unidade,
        "nome_produto_normalizado": nome_normalizado,
        "nome_exibicao": nome_exibicao,
        "item_base": item_base,
        "tipo_produto": tipo_str or None,
        "marca_id": slug_marca if marca else None,
        "marca_nome": marca.title() if marca else None,
        "categoria_id": categoria_id,
        "embalagem": embalagem,
        "quantidade_embalagem": qtd_emb,
        "unidade_medida": un_medida,
        "unidade_padrao": un_padrao,
        "fator_conversao_padrao": fator_padrao,
        "preco_por_unidade": preco_por_unidade,
        "gtin": gtin,
        "tokens_busca": sorted(list(tokens_set))[:25],
    }


def avaliar_correspondencia_produtos(prod_a: Dict, prod_b: Dict) -> str:
    """
    Determina o nível de correspondência entre dois produtos normalizados:
    - 'EXATA': Mesmo GTIN válido OU mesmo (item_base, tipo_produto, marca_id, quantidade_embalagem, unidade_medida)
    - 'EQUIVALENTE': Mesmo (item_base, tipo_produto, quantidade_embalagem, unidade_medida) de marcas diferentes,
                     OU mesmo (item_base, tipo_produto, marca_id) com preço por unidade padronizada compatível
    - 'APROXIMADA': Mesmo item_base e unidade_padrao, mas tipo/marca não especificados em um dos lados
    - 'SEM_CORRESPONDENCIA': Produtos diferentes, tipos conflitantes (ex: Integral vs Desnatado) ou medidas diretas incompatíveis.
    """
    # 1. Tipos mutuamente exclusivos (ex: Leite Integral vs Leite Desnatado) NUNCA combinam
    tipo_a = prod_a.get("tipo_produto")
    tipo_b = prod_b.get("tipo_produto")
    if tipo_a and tipo_b and tipo_a != tipo_b:
        return "SEM_CORRESPONDENCIA"

    # 2. Se ambos possuem GTIN e são iguais -> EXATA; se ambos possuem GTIN e são diferentes -> verifica atributos
    gtin_a = prod_a.get("gtin")
    gtin_b = prod_b.get("gtin")
    if gtin_a and gtin_b and gtin_a == gtin_b:
        return "EXATA"

    # 3. Item base diferente -> SEM_CORRESPONDENCIA
    base_a = prod_a.get("item_base", "")
    base_b = prod_b.get("item_base", "")
    if not base_a or not base_b:
        return "SEM_CORRESPONDENCIA"

    # Verifica interseção do item base principal (primeira palavra substantiva deve coincidir: ex ARROZ == ARROZ)
    prim_a = base_a.split()[0]
    prim_b = base_b.split()[0]
    if prim_a != prim_b:
        return "SEM_CORRESPONDENCIA"

    mesma_medida = (
        prod_a.get("unidade_medida") == prod_b.get("unidade_medida")
        and abs(float(prod_a.get("quantidade_embalagem", 1.0)) - float(prod_b.get("quantidade_embalagem", 1.0))) < 0.001
    )

    marca_a = prod_a.get("marca_id")
    marca_b = prod_b.get("marca_id")

    # Arroz 5 kg NÃO pode ser comparado diretamente como exato com Arroz 1 kg
    if not mesma_medida:
        return "SEM_CORRESPONDENCIA"

    # Mesma medida, mesmo item base e tipos compatíveis
    if base_a == base_b and tipo_a == tipo_b:
        if marca_a and marca_b:
            if marca_a == marca_b:
                return "EXATA"
            else:
                # Café ou Arroz de outra marca: nunca é EXATA, é EQUIVALENTE (claramente identificado)
                return "EQUIVALENTE"
        elif not marca_a and not marca_b:
            return "EXATA"
        else:
            return "APROXIMADA"

    if prim_a == prim_b and mesma_medida:
        return "APROXIMADA"

    return "SEM_CORRESPONDENCIA"

