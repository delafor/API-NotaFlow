import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas import ItemNotaSchema, NotaFiscalSchema, gerar_id_deterministico_nota


def test_validacao_item_sucesso():
    item = ItemNotaSchema(
        nome="REFRIGERANTE COCA COLA 2L",
        codigo="1234",
        quantidade=2.0,
        unidade="UN",
        valor_unitario=8.50,
        valor_total=17.00,
    )
    assert item.quantidade == 2.0
    assert item.valor_total == 17.00


def test_validacao_item_invalido():
    # Quantidade <= 0 deve falhar
    try:
        ItemNotaSchema(
            nome="PRODUTO X",
            quantidade=0.0,
            valor_unitario=10.0,
            valor_total=0.0,
        )
        assert False, "Deveria ter lançado erro de validação para quantidade <= 0"
    except Exception:
        pass


def test_validacao_nota_fiscal_nfce():
    nota_dict = {
        "tipo": "NFC-e",
        "estabelecimento": "MERCADO EXEMPLO LTDA",
        "total": 27.00,
        "chave": "29260903184187000119650090000069531012240675",
        "numero": "6953",
        "serie": "9",
        "emissao": "29/09/2026 15:46:01",
        "produtos": [
            {
                "nome": "ARROZ 1KG",
                "quantidade": 2.0,
                "unidade": "UN",
                "valor_unitario": 6.00,
                "valor_total": 12.00,
            },
            {
                "nome": "CARNE BOVINA",
                "quantidade": 0.5,
                "unidade": "KG",
                "valor_unitario": 30.00,
                "preco_kg": 30.00,
                "valor_total": 15.00,
            },
        ],
    }

    schema = NotaFiscalSchema(**nota_dict)
    assert schema.tipo == "NFC-e"
    assert len(schema.produtos) == 2
    assert schema.total == 27.00


def test_validacao_nota_bpe():
    bpe_dict = {
        "tipo": "BP-e",
        "estabelecimento": "VIACAO CIDADE SOL",
        "origem": "MUTUIPE (BA)",
        "destino": "SANTA INES (BA)",
        "total": 21.00,
        "tarifa": 16.75,
        "seguro": 4.25,
        "numero": "33251242",
        "serie": "878",
        "chave": "29260914602189000105638780332512421585083560",
        "produtos": [],
    }
    schema = NotaFiscalSchema(**bpe_dict)
    assert schema.tipo == "BP-e"
    assert schema.total == 21.00


def test_geracao_id_deterministico():
    nota_1 = {
        "chave": "29260903184187000119650090000069531012240675",
        "total": 55.96,
    }
    id_1 = gerar_id_deterministico_nota(nota_1)
    id_2 = gerar_id_deterministico_nota(nota_1)
    assert id_1 == id_2
    assert id_1.startswith("chave_29260903184187000119650090000069531012240675")

    nota_sem_chave = {
        "numero": "12345",
        "serie": "1",
        "estabelecimento": "POSTO ABC",
        "total": 150.00,
    }
    id_hash_1 = gerar_id_deterministico_nota(nota_sem_chave)
    id_hash_2 = gerar_id_deterministico_nota(nota_sem_chave)
    assert id_hash_1 == id_hash_2
    assert id_hash_1.startswith("doc_")


if __name__ == "__main__":
    test_validacao_item_sucesso()
    test_validacao_item_invalido()
    test_validacao_nota_fiscal_nfce()
    test_validacao_nota_bpe()
    test_geracao_id_deterministico()
    print("Todos os testes de regras de negócio em test_schemas.py passaram com sucesso!")

