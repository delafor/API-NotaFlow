import re
import logging
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def limpar_texto(texto: str) -> str:
    return " ".join(texto.split())


def valor_monetario(texto: str):
    if not texto:
        return None

    texto = texto.strip()
    texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return None


def extrair_nota(html: str):
    logger.debug("Iniciando extração da nota fiscal a partir do HTML")

    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)

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

    # ==========================================================
    # RESULTADO
    # ==========================================================

    return {
        "tipo": "BP-e",
        "estabelecimento": estabelecimento,
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
        nome_elemento = item.select_one(".txtTit")

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

        # Código
        elemento = item.select_one(".RCod")

        if elemento:
            match = re.search(
                r"Código:\s*(\d+)",
                elemento.get_text(),
            )

            if match:
                codigo = match.group(1)

        # Quantidade
        elemento = item.select_one("qtd")

        if elemento:
            match = re.search(
                r"Qtde\.\s*([\d,.]+)",
                elemento.get_text(),
            )

            if match:
                quantidade = valor_monetario(
                    match.group(1)
                )

        # Unidade
        elemento = item.select_one(".RUN")

        if elemento:
            match = re.search(
                r"UN:\s*(.*)",
                elemento.get_text(),
            )

            if match:
                unidade = limpar_texto(
                    match.group(1)
                )

        # Valor unitário
        elemento = item.select_one(".RvlUnit")

        if elemento:
            match = re.search(
                r"Vl\. Unit\.\s*([\d,.]+)",
                elemento.get_text(),
            )

            if match:
                valor_unitario = valor_monetario(
                    match.group(1)
                )

        # Valor total
        elemento = item.select_one(".valor")

        if elemento:
            valor_total = valor_monetario(
                elemento.get_text()
            )

        produtos.append(
            {
                "nome": nome,
                "codigo": codigo,
                "quantidade": quantidade,
                "unidade": unidade,
                "valor_unitario": valor_unitario,
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

    return {
        "tipo": "NFC-e",
        "estabelecimento": estabelecimento,
        "produtos": produtos,
        "total": total,
    }