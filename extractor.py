import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Mapeamento oficial IBGE de código UF (primeiros 2 dígitos da chave de acesso fiscal)
COD_UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA", "16": "AP", "17": "TO",
    "21": "MA", "22": "PI", "23": "CE", "24": "RN", "25": "PB", "26": "PE", "27": "AL",
    "28": "SE", "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP", "41": "PR",
    "42": "SC", "43": "RS", "50": "MS", "51": "MT", "52": "GO", "53": "DF",
}

UFS_VALIDAS = set(COD_UF_IBGE.values())


def limpar_texto(texto: str) -> str:
    return " ".join(texto.split())


def validar_gtin_ean(codigo: str) -> bool:
    """Valida dígito verificador padrão GS1 (GTIN-8, GTIN-12, GTIN-13, GTIN-14)."""
    if not codigo or not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False
    # Códigos iniciados por 2 são de peso variável interno de balança (não são GTIN universal)
    if codigo.startswith("2") and len(codigo) == 13:
        return False
    digitos = [int(d) for d in codigo]
    check = digitos[-1]
    corpo = digitos[:-1]
    soma = 0
    for idx, d in enumerate(reversed(corpo)):
        soma += d * (3 if idx % 2 == 0 else 1)
    calculado = (10 - (soma % 10)) % 10
    return check == calculado


def extrair_gtin_produto(nome: str, codigo: str = None):
    """Extrai GTIN/EAN confiável do prefixo do nome ou do campo código da nota."""
    if nome:
        match_prefix = re.match(r"^\s*(\d{8,14})\s*-\s*", nome)
        if match_prefix:
            cand = match_prefix.group(1)
            if validar_gtin_ean(cand):
                return cand
    if codigo:
        cand_cod = re.sub(r"\D", "", str(codigo))
        if validar_gtin_ean(cand_cod):
            return cand_cod
    return None


def extrair_dados_emitente(soup: BeautifulSoup, chave: str = None) -> dict:
    """
    Extrai CNPJ, endereço comercial, município, UF e código IBGE do cabeçalho da nota
    (.txtCenter .text) com fallback determinístico pela chave de acesso de 44 dígitos.
    """
    cnpj = None
    endereco = None
    municipio = None
    uf = None
    codigo_ibge = None

    textos = [limpar_texto(el.get_text(" ", strip=True)) for el in soup.select(".txtCenter .text")]

    for t in textos:
        if not t:
            continue
        # Verifica CNPJ formatado ou numérico
        match_cnpj = re.search(r"(\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2})", t)
        if match_cnpj and not cnpj:
            cnpj_limpo = re.sub(r"\D", "", match_cnpj.group(1))
            if len(cnpj_limpo) == 14:
                cnpj = cnpj_limpo
            continue

        # Se contém vírgulas e não é apenas CNPJ, trata como endereço do emitente
        if "," in t and not endereco:
            endereco = t
            partes = [p.strip() for p in t.split(",") if p.strip()]
            if len(partes) >= 2:
                cand_uf = partes[-1].upper().strip()
                if cand_uf in UFS_VALIDAS:
                    uf = cand_uf
                    cand_mun = partes[-2].strip()
                    # Verifica formato "2927408 - SALVADOR"
                    match_ibge_mun = re.match(r"^(\d{7})\s*-\s*(.+)$", cand_mun)
                    if match_ibge_mun:
                        codigo_ibge = match_ibge_mun.group(1)
                        municipio = match_ibge_mun.group(2).strip().upper()
                    else:
                        municipio = cand_mun.upper()

    # Fallback determinístico via Chave de Acesso de 44 dígitos (posições UF e CNPJ)
    if chave:
        chave_limpa = re.sub(r"\D", "", str(chave))
        if len(chave_limpa) == 44:
            if not uf:
                uf = COD_UF_IBGE.get(chave_limpa[:2])
            if not cnpj:
                cnpj_chave = chave_limpa[6:20]
                if len(cnpj_chave) == 14 and cnpj_chave.isdigit():
                    cnpj = cnpj_chave

    return {
        "cnpj": cnpj,
        "endereco": endereco,
        "municipio": municipio,
        "uf": uf,
        "codigo_ibge": codigo_ibge,
    }


def valor_monetario(texto: str):
    if not texto:
        return None

    texto = texto.strip()
    if "," in texto and "." in texto:
        texto = texto.replace(".", "").replace(",", ".")
    elif "," in texto:
        texto = texto.replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def extrair_nota(html: str):
    logger.debug("Iniciando extração da nota fiscal a partir do HTML")

    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)

    # Fallback para SEFAZ-BA caso o conteúdo da nota esteja embutido no __VIEWSTATE
    if soup.select_one("#tabResult") is None and "BILHETE DE PASSAGEM" not in texto:
        vs_input = soup.find("input", {"name": "__VIEWSTATE"})
        if vs_input and vs_input.get("value"):
            try:
                import base64
                raw_vs = base64.b64decode(vs_input.get("value"))
                decoded_vs = raw_vs.decode("utf-8", errors="ignore")
                if "tabResult" in decoded_vs or "txtTopo" in decoded_vs:
                    start_div = decoded_vs.find("<div")
                    if start_div != -1:
                        soup = BeautifulSoup(decoded_vs[start_div:], "html.parser")
                        texto = soup.get_text(" ", strip=True)
            except Exception:
                pass

    # BP-e
    if (
        "BILHETE DE PASSAGEM ELETRÔNICO" in texto
        or soup.find(id="logoTopoBPe") is not None
    ):
        return extrair_bpe(soup)

    # NFC-e
    if (
        soup.select_one("#tabResult") is not None
        or "NFC-e" in texto
        or "Nota Fiscal de Consumidor Eletrônica" in texto
    ):
        return extrair_nfce(soup)

    raise ValueError("Tipo de documento fiscal não reconhecido.")


def extrair_bpe(soup: BeautifulSoup):
    # ==========================================================
    # ESTABELECIMENTO
    # ==========================================================

    elemento = soup.select_one("#u20")

    estabelecimento = (
        limpar_texto(elemento.get_text())
        if elemento
        else None
    )

    # ==========================================================
    # ORIGEM
    # ==========================================================

    elemento = soup.select_one("#lineD .txtBlue")

    origem = (
        limpar_texto(elemento.get_text())
        if elemento
        else None
    )

    # ==========================================================
    # DESTINO
    # ==========================================================

    elemento = soup.select_one("#lineE .txtBlue")

    destino = (
        limpar_texto(elemento.get_text())
        if elemento
        else None
    )

    # ==========================================================
    # DATA E HORÁRIO DA VIAGEM
    # ==========================================================

    data_hora = None

    elemento = soup.select_one("#lineOD")

    if elemento:
        texto_data = limpar_texto(
            elemento.get_text(" ", strip=True)
        )

        match = re.search(
            r"Data e horário:\s*(\d{2}/\d{2}/\d{4})\s*às\s*([0-9:]+)",
            texto_data,
        )

        if match:
            data_hora = (
                f"{match.group(1)} {match.group(2)}"
            )

    # ==========================================================
    # POLTRONA
    # ==========================================================

    poltrona = None

    elementos = soup.select(".txtOD")

    if elementos:
        poltrona = limpar_texto(
            elementos[0].get_text()
        )

    # ==========================================================
    # PREFIXO / LINHA / TIPO
    # ==========================================================

    prefixo = None
    linha = None
    tipo_viagem = None

    for bloco in soup.select("#linha_viagem .ui-grid-b > div"):
        label = bloco.find("label")
        span = bloco.find("span")

        if not label or not span:
            continue

        nome = limpar_texto(label.get_text())
        valor = limpar_texto(span.get_text())

        if "Prefixo" in nome:
            prefixo = valor

        elif "Linha" in nome:
            linha = valor

        elif "Tipo" in nome:
            tipo_viagem = valor

    # ==========================================================
    # VALORES
    # ==========================================================

    valores = {}

    for linha_total in soup.select(
        "#totalNota #linhaTotal"
    ):
        label = linha_total.find("label")
        span = linha_total.find(
            "span",
            class_="totalNumb",
        )

        if not label or not span:
            continue

        nome = limpar_texto(
            label.get_text()
        )

        valor = limpar_texto(
            span.get_text()
        )

        valores[nome] = valor_monetario(valor)

    tarifa = valores.get("Tarifa")
    seguro = valores.get("Seguro")
    valor_total = valores.get("Valor total")
    desconto = valores.get("Desconto")
    valor_pagar = valores.get("Valor a pagar")

    # ==========================================================
    # PAGAMENTO
    # ==========================================================

    forma_pagamento = None
    valor_pago = None
    troco = None

    for linha_total in soup.select(
        "#totalNota #linhaTotal"
    ):
        label = linha_total.find("label")
        span = linha_total.find("span")

        if not label or not span:
            continue

        nome = limpar_texto(
            label.get_text()
        )

        valor = limpar_texto(
            span.get_text()
        )

        if nome in [
            "Dinheiro",
            "Cartão",
            "PIX",
        ]:
            forma_pagamento = nome
            valor_pago = valor_monetario(valor)

        elif "Troco" in nome:
            troco = valor_monetario(valor)

    # ==========================================================
    # IDENTIFICAÇÃO DO BP-e
    # ==========================================================

    numero = None
    serie = None
    emissao = None
    protocolo = None

    for info in soup.select("#infos li"):
        texto_info = limpar_texto(
            info.get_text(" ", strip=True)
        )

        match = re.search(
            r"Número:\s*(\d+)",
            texto_info,
        )

        if match:
            numero = match.group(1)

        match = re.search(
            r"Série:\s*(\d+)",
            texto_info,
        )

        if match:
            serie = match.group(1)

        match = re.search(
            r"Emissão:\s*(\d{2}/\d{2}/\d{4})\s*-\s*([0-9:]+)",
            texto_info,
        )

        if match:
            emissao = (
                f"{match.group(1)} "
                f"{match.group(2)}"
            )

        match = re.search(
            r"Protocolo de Autorização:\s*(\d+)",
            texto_info,
        )

        if match:
            protocolo = match.group(1)

    # ==========================================================
    # CHAVE DE ACESSO
    # ==========================================================

    chave = None

    elemento = soup.select_one(".chave")

    if elemento:
        chave = limpar_texto(
            elemento.get_text()
        ).replace(".", "")

    dados_emitente = extrair_dados_emitente(soup, chave)

    # ==========================================================
    # RESULTADO
    # ==========================================================

    return {
        "tipo": "BP-e",
        "estabelecimento": estabelecimento,
        "cnpj": dados_emitente["cnpj"],
        "endereco": dados_emitente["endereco"],
        "municipio": dados_emitente["municipio"],
        "uf": dados_emitente["uf"],
        "codigo_ibge": dados_emitente["codigo_ibge"],
        "origem": origem,
        "destino": destino,
        "data_hora": data_hora,
        "poltrona": poltrona,
        "prefixo": prefixo,
        "linha": linha,
        "tipo_viagem": tipo_viagem,
        "tarifa": tarifa,
        "seguro": seguro,
        "total": valor_total,
        "desconto": desconto,
        "valor_pagar": valor_pagar,
        "forma_pagamento": forma_pagamento,
        "valor_pago": valor_pago,
        "troco": troco,
        "numero": numero,
        "serie": serie,
        "emissao": emissao,
        "protocolo": protocolo,
        "chave": chave,
        "produtos": [],
    }


def extrair_nfce(soup: BeautifulSoup):
    # ==========================================================
    # ESTABELECIMENTO
    # ==========================================================

    elemento = soup.select_one("#u20")

    estabelecimento = (
        limpar_texto(elemento.get_text())
        if elemento
        else None
    )

    produtos = []

    # ==========================================================
    # PRODUTOS
    # ==========================================================

    for item in soup.select("#tabResult tr"):
        nome_elemento = item.select_one(".txtTit") or item.select_one(".txtTit2")

        if not nome_elemento:
            continue

        nome = limpar_texto(
            nome_elemento.get_text()
        )

        codigo = None
        quantidade = None
        unidade = None
        valor_unitario = None
        valor_total = None

        texto_linha = limpar_texto(item.get_text(" ", strip=True))

        # Código
        elemento = item.select_one(".RCod")

        if elemento:
            match = re.search(
                r"C[oó]digo\s*:?\s*(\d+)",
                elemento.get_text(),
                re.IGNORECASE,
            )

            if match:
                codigo = match.group(1)

        # Quantidade (suporta .Rqtd, Qtde.:, Qtd.:, etc.)
        elemento = item.select_one(".Rqtd") or item.select_one("qtd")

        if elemento:
            texto_qtd = limpar_texto(elemento.get_text())
            match = re.search(
                r"(?:Qtde|Qtd)\.?\s*:?\s*([\d.,]+)",
                texto_qtd,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(r"([\d.,]+)", texto_qtd)

            if match:
                quantidade = valor_monetario(
                    match.group(1)
                )
        else:
            match = re.search(
                r"(?:Qtde|Qtd)\.?\s*:?\s*([\d.,]+)",
                texto_linha,
                re.IGNORECASE,
            )
            if match:
                quantidade = valor_monetario(match.group(1))

        # Unidade (UN, KG, L, PC, etc.)
        elemento = item.select_one(".RUN")

        if elemento:
            texto_un = limpar_texto(elemento.get_text())
            match = re.search(
                r"UN\.?\s*:?\s*([A-Za-z0-9]+)",
                texto_un,
                re.IGNORECASE,
            )

            if match:
                unidade = limpar_texto(
                    match.group(1)
                ).upper()
            else:
                limpo = re.sub(r"^UN\.?\s*:?\s*", "", texto_un, flags=re.IGNORECASE).strip()
                if limpo:
                    unidade = limpo.upper()
        else:
            match = re.search(
                r"\bUN\.?\s*:?\s*([A-Za-z0-9]+)",
                texto_linha,
                re.IGNORECASE,
            )
            if match:
                unidade = match.group(1).strip().upper()

        # Valor unitário (preço por UN ou preço do KG na nota)
        elemento = item.select_one(".RvlUnit")

        if elemento:
            texto_unit = limpar_texto(elemento.get_text())
            match = re.search(
                r"Vl(?:r)?\.?\s*Unit\.?\s*:?\s*(?:R\$\s*)?([\d.,]+)",
                texto_unit,
                re.IGNORECASE,
            )
            if not match:
                match = re.search(r"([\d.,]+)", texto_unit)

            if match:
                valor_unitario = valor_monetario(
                    match.group(1)
                )
        else:
            match = re.search(
                r"Vl(?:r)?\.?\s*Unit\.?\s*:?\s*(?:R\$\s*)?([\d.,]+)",
                texto_linha,
                re.IGNORECASE,
            )
            if match:
                valor_unitario = valor_monetario(match.group(1))

        # Valor total
        elemento = item.select_one(".valor")

        if elemento:
            valor_total = valor_monetario(
                elemento.get_text()
            )

        # Fallbacks matemáticos caso algum campo venha omitido na nota
        if valor_unitario is None and valor_total is not None and quantidade and quantidade > 0:
            valor_unitario = round(valor_total / quantidade, 2)

        if valor_total is None and valor_unitario is not None and quantidade is not None:
            valor_total = round(valor_unitario * quantidade, 2)

        if not unidade:
            unidade = "UN"

        eh_kg = unidade in ("KG", "KILO", "QUILO", "KG.")
        if eh_kg:
            unidade = "KG"

        preco_kg = valor_unitario if eh_kg else None
        gtin = extrair_gtin_produto(nome, codigo)

        produtos.append(
            {
                "nome": nome,
                "codigo": codigo,
                "gtin": gtin,
                "quantidade": quantidade,
                "unidade": unidade,
                "valor_unitario": valor_unitario,
                "preco_kg": preco_kg,
                "valor_total": valor_total,
            }
        )

    # ==========================================================
    # TOTAL
    # ==========================================================

    total = None

    elemento = soup.select_one(".txtMax")

    if elemento:
        texto_total = limpar_texto(
            elemento.get_text()
        )

        match = re.search(
            r"([\d.,]+)",
            texto_total,
        )

        if match:
            total = valor_monetario(
                match.group(1)
            )

    # ==========================================================
    # IDENTIFICAÇÃO DA NFC-e E CHAVE DE ACESSO
    # ==========================================================
    numero = None
    serie = None
    emissao = None
    chave = None

    for info in soup.select("#infos li, #infos div"):
        texto_info = limpar_texto(info.get_text(" ", strip=True))

        if not numero:
            match = re.search(r"Número:\s*(\d+)", texto_info, re.IGNORECASE)
            if match:
                numero = match.group(1)

        if not serie:
            match = re.search(r"Série:\s*(\d+)", texto_info, re.IGNORECASE)
            if match:
                serie = match.group(1)

        if not emissao:
            match = re.search(r"Emissão:\s*(\d{2}/\d{2}/\d{4}(?:\s*-\s*|\s+)[0-9:]+)", texto_info, re.IGNORECASE)
            if match:
                emissao = match.group(1)

    elemento_chave = soup.select_one(".chave")
    if elemento_chave:
        chave = re.sub(r"\D", "", elemento_chave.get_text())
    else:
        # Tenta encontrar no texto geral
        texto_geral = soup.get_text(" ", strip=True)
        match_chave = re.search(r"Chave de acesso:\s*([\d\s.]{44,60})", texto_geral, re.IGNORECASE)
        if match_chave:
            chave = re.sub(r"\D", "", match_chave.group(1))

    dados_emitente = extrair_dados_emitente(soup, chave)

    return {
        "tipo": "NFC-e",
        "estabelecimento": estabelecimento,
        "cnpj": dados_emitente["cnpj"],
        "endereco": dados_emitente["endereco"],
        "municipio": dados_emitente["municipio"],
        "uf": dados_emitente["uf"],
        "codigo_ibge": dados_emitente["codigo_ibge"],
        "produtos": produtos,
        "total": total,
        "numero": numero,
        "serie": serie,
        "emissao": emissao,
        "chave": chave,
    }