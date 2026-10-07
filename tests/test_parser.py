import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extractor import extrair_nota

base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
html_path = os.path.join(base_dir, "nota.html")

if os.path.exists(html_path):
    with open(html_path, "r", encoding="utf-8") as arquivo:
        html = arquivo.read()

    nota = extrair_nota(html)
    print("Resultado da extração:")
    print(nota)
else:
    print(f"Arquivo {html_path} não encontrado para o teste.")