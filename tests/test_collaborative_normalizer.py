import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collaborative.establishment_resolver import (
    extrair_cnpj_da_chave,
    resolver_estabelecimento,
    validar_cnpj,
)
from collaborative.normalizer import (
    avaliar_correspondencia_produtos,
    normalizar_produto,
)


def test_arroz_5kg_nao_compara_com_arroz_1kg():
    arroz_5kg = normalizar_produto("ARROZ TIPO 1 CAMIL 5KG", preco_praticado=29.90)
    arroz_1kg = normalizar_produto("ARROZ TIPO 1 CAMIL 1KG", preco_praticado=6.90)

    assert arroz_5kg["produto_id"] != arroz_1kg["produto_id"]
    assert arroz_5kg["quantidade_embalagem"] == 5.0
    assert arroz_1kg["quantidade_embalagem"] == 1.0
    assert arroz_5kg["preco_por_unidade"] == 5.98  # R$ 29,90 / 5 kg = R$ 5,98/kg
    assert avaliar_correspondencia_produtos(arroz_5kg, arroz_1kg) == "SEM_CORRESPONDENCIA"


def test_leite_integral_nao_compara_com_leite_desnatado():
    leite_int = normalizar_produto("LEITE UHT INTEGRAL PIRACANJUBA 1L", preco_praticado=5.49)
    leite_desn = normalizar_produto("LEITE UHT DESNATADO PIRACANJUBA 1L", preco_praticado=5.49)

    assert leite_int["produto_id"] != leite_desn["produto_id"]
    assert leite_int["tipo_produto"] == "INTEGRAL"
    assert leite_desn["tipo_produto"] == "DESNATADO"
    assert avaliar_correspondencia_produtos(leite_int, leite_desn) == "SEM_CORRESPONDENCIA"


def test_cafe_marcas_diferentes_nao_eh_exata():
    cafe_pilao = normalizar_produto("CAFE TORRADO E MOIDO TRADICIONAL PILAO 500G", preco_praticado=18.90)
    cafe_melitta = normalizar_produto("CAFE TORRADO E MOIDO TRADICIONAL MELITTA 500G", preco_praticado=19.90)

    assert cafe_pilao["produto_id"] != cafe_melitta["produto_id"]
    assert cafe_pilao["marca_id"] == "pilao"
    assert cafe_melitta["marca_id"] == "melitta"
    # Preço por KG padronizado (500g = 0.5kg -> 18.90 / 0.5 = 37.80/kg)
    assert cafe_pilao["preco_por_unidade"] == 37.80
    assert avaliar_correspondencia_produtos(cafe_pilao, cafe_melitta) == "EQUIVALENTE"


def test_abreviacoes_supermercado_convergem_para_exata():
    desc_1 = normalizar_produto("1042 - ARR T1 CAMIL PCT 5KG", preco_praticado=25.90)
    desc_2 = normalizar_produto("ARROZ TIPO 1 CAMIL 5 KG", preco_praticado=29.90)

    assert desc_1["produto_id"] == desc_2["produto_id"]
    assert avaliar_correspondencia_produtos(desc_1, desc_2) == "EXATA"


def test_extracao_gtin_ean13_valido():
    prod = normalizar_produto(
        "7891249054328 - REGULADOR ALIANCA 506 01 GR. S MANG. ALIANCA",
        preco_praticado=48.0,
    )
    assert prod["gtin"] == "7891249054328"
    assert prod["produto_id"] == "gtin_7891249054328"


def test_padronizacao_estabelecimentos_variacoes_escrita():
    e1 = resolver_estabelecimento("Mercado Central", cidade_id="2928901", nome_cidade="Santa Inês", uf="BA")
    e2 = resolver_estabelecimento("MERCADO CENTRAL", cidade_id="2928901", nome_cidade="Santa Inês", uf="BA")
    e3 = resolver_estabelecimento("Merc. Central LTDA", cidade_id="2928901", nome_cidade="Santa Inês", uf="BA")

    assert e1["estabelecimento_id"] == e2["estabelecimento_id"] == e3["estabelecimento_id"]
    assert e1["nome_exibicao"] == "Mercado Central"

    # Mesmo nome em outra cidade NÃO deve ser unido
    e_outra_cidade = resolver_estabelecimento("Mercado Central", cidade_id="2918001", nome_cidade="Jequié", uf="BA")
    assert e1["estabelecimento_id"] != e_outra_cidade["estabelecimento_id"]


def test_diferenciacao_filiais_por_cnpj_e_chave():
    chave_nfce = "29260903184187000119650090000069531012240675"
    cnpj_extraido = extrair_cnpj_da_chave(chave_nfce)
    assert cnpj_extraido == "03184187000119"
    assert validar_cnpj("03.184.187/0001-19") == "03184187000119"

    matriz = resolver_estabelecimento("Rede Mercado X", cnpj_bruto="03.184.187/0001-19")
    # CNPJ de filial diferente (/0002-08)
    filial_2 = resolver_estabelecimento(
        "Rede Mercado X",
        cnpj_bruto="03.184.187/0002-08",
        endereco_comercial="AV BRASIL, 500, CENTRO, SALVADOR, BA",
    )
    assert matriz["estabelecimento_id"] != filial_2["estabelecimento_id"]
    assert matriz["estabelecimento_id"] == "cnpj_03184187000119"
    assert filial_2["estabelecimento_id"] == "cnpj_03184187000208"

