import logging
import urllib.parse
from bs4 import BeautifulSoup
from security import safe_http_request

logger = logging.getLogger(__name__)


def buscar_pagina(url: str) -> str:
    """
    Safely fetches a fiscal page (BP-e / NFC-e) by URL.
    Handles intermediate forms (e.g., #frmConsultaQrCode) safely using safe_http_request.
    All URLs (initial GET, redirects, form actions) pass through anti-SSRF validation.
    """
    logger.info("Iniciando busca segura da página fiscal")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/153.0.0.0 Safari/537.36"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9",
    }

    # ----------------------------------------------------------
    # PRIMEIRO GET SEGURO
    # ----------------------------------------------------------
    html_text, final_url, response = safe_http_request(
        url=url,
        method="GET",
        headers=headers,
    )

    # ----------------------------------------------------------
    # VERIFICA SE JÁ É O BP-e FINAL
    # ----------------------------------------------------------
    if "BILHETE DE PASSAGEM ELETRÔNICO" in html_text:
        logger.info("BP-e encontrado diretamente na resposta.")
        return html_text

    # ----------------------------------------------------------
    # VERIFICA SE É A PÁGINA INTERMEDIÁRIA
    # ----------------------------------------------------------
    soup = BeautifulSoup(html_text, "html.parser")
    formulario = soup.select_one("#frmConsultaQrCode")

    if formulario:
        logger.info("Página intermediária do BP-e encontrada. Extraindo formulário...")

        dados = {}
        for campo in formulario.select("input"):
            nome = campo.get("name")
            valor = campo.get("value")
            if nome:
                dados[nome] = valor or ""

        action = formulario.get("action")
        if not action:
            raise ValueError("Formulário BP-e não possui o atributo 'action'.")

        # Resolve relative action URL against the final validated URL
        url_post = urllib.parse.urljoin(final_url, action)

        logger.info("Enviando POST seguro para página intermediária...")

        html_post_text, final_post_url, response_post = safe_http_request(
            url=url_post,
            method="POST",
            data=dados,
            headers={
                **headers,
                "Referer": final_url,
            },
        )

        return html_post_text

    # ----------------------------------------------------------
    # RETORNO PADRÃO
    # ----------------------------------------------------------
    return html_text


def extrair_texto(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator="\n", strip=True)