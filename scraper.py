from bs4 import BeautifulSoup
import requests


def buscar_pagina(url: str) -> str:

    resposta = requests.get(
        url,
        timeout=15,
        headers={
            "User-Agent": "Mozilla/5.0"
        }
    )

    resposta.raise_for_status()

    return resposta.text


def extrair_texto(html: str):

    soup = BeautifulSoup(html, "html.parser")

    return soup.get_text(
        separator="\n",
        strip=True
    )