import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from extractor import extrair_nota


def test_extrair_bpe_sample():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    html_path = os.path.join(base_dir, "nota.html")

    if os.path.exists(html_path):
        with open(html_path, "r", encoding="utf-8") as arquivo:
            html = arquivo.read()

        nota = extrair_nota(html)
        assert nota["tipo"] == "BP-e"
        assert nota["estabelecimento"] == "VIACAO JEQUIE CIDADE SOL LTDA"
        assert nota["total"] == 21.0


def test_extrair_nfce_quantidade_unidade_e_kg():
    sample_nfce_html = """
    <html>
      <body>
        <div id="u20">SUPERMERCADO EXEMPLO LTDA</div>
        <table id="tabResult">
          <tr id="Item + 1">
            <td>
              <span class="txtTit">ARROZ BRANCO TIPO 1</span>
              <span class="RCod">(Código: 78910001)</span>
              <span class="Rqtd"><strong>Qtde.:</strong>3,000</span>
              <span class="RUN"><strong>UN: </strong>UN</span>
              <span class="RvlUnit"><strong>Vl. Unit.:</strong> 6,49</span>
            </td>
            <td>
              <span class="valor">19,47</span>
            </td>
          </tr>
          <tr id="Item + 2">
            <td>
              <span class="txtTit">CARNE BOVINA PATINHO</span>
              <span class="RCod">(Código: 2045)</span>
              <span class="Rqtd"><strong>Qtde.:</strong>0,850</span>
              <span class="RUN"><strong>UN: </strong>KG</span>
              <span class="RvlUnit"><strong>Vl. Unit.:</strong> 42,90</span>
            </td>
            <td>
              <span class="valor">36,47</span>
            </td>
          </tr>
        </table>
        <span class="txtMax">55,94</span>
      </body>
    </html>
    """

    nota = extrair_nota(sample_nfce_html)
    assert nota["tipo"] == "NFC-e"
    assert nota["estabelecimento"] == "SUPERMERCADO EXEMPLO LTDA"
    assert nota["total"] == 55.94
    assert len(nota["produtos"]) == 2

    # Produto 1: Unidade (UN)
    prod_un = nota["produtos"][0]
    assert prod_un["nome"] == "ARROZ BRANCO TIPO 1"
    assert prod_un["codigo"] == "78910001"
    assert prod_un["quantidade"] == 3.0
    assert prod_un["unidade"] == "UN"
    assert prod_un["valor_unitario"] == 6.49
    assert prod_un["preco_kg"] is None
    assert prod_un["valor_total"] == 19.47

    # Produto 2: Quilo (KG)
    prod_kg = nota["produtos"][1]
    assert prod_kg["nome"] == "CARNE BOVINA PATINHO"
    assert prod_kg["codigo"] == "2045"
    assert prod_kg["quantidade"] == 0.85
    assert prod_kg["unidade"] == "KG"
    assert prod_kg["valor_unitario"] == 42.90
    assert prod_kg["preco_kg"] == 42.90
    assert prod_kg["valor_total"] == 36.47


if __name__ == "__main__":
    test_extrair_bpe_sample()
    test_extrair_nfce_quantidade_unidade_e_kg()
    print("Testes de extração NFC-e (UN e KG) e BP-e passaram com sucesso!")