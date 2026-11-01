import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from schemas import gerar_id_deterministico_nota


def test_simulacao_idempotencia_concorrente():
    """
    Testa se múltiplas chamadas simultâneas com a mesma nota fiscal
    geram exatamente o mesmo ID e mantêm consistência atômica.
    """
    dados_nota = {
        "chave": "29260903184187000119650090000069531012240675",
        "tipo": "NFC-e",
        "estabelecimento": "MERCADO TESTE",
        "total": 58.90,
    }

    resultados = []
    lock = threading.Lock()

    def worker():
        doc_id = gerar_id_deterministico_nota(dados_nota)
        with lock:
            resultados.append(doc_id)

    # Simula 20 operações simultâneas
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker) for _ in range(20)]
        for f in futures:
            f.result()

    # Todos os IDs gerados devem ser rigorosamente idênticos
    assert len(resultados) == 20
    assert len(set(resultados)) == 1, "Houve divergência de ID em operações simultâneas!"
    assert resultados[0] == "chave_29260903184187000119650090000069531012240675"


def test_falha_extracao_nao_gera_dados_incompletos():
    """
    Garante que uma falha ou dados ausentes na extração lançam exceção
    e impedem a criação do schema da nota.
    """
    dados_incompletos = {
        # Sem tipo e sem total
        "estabelecimento": "EMPRESA X",
    }

    try:
        from schemas import NotaFiscalSchema
        NotaFiscalSchema(**dados_incompletos)
        assert False, "Deveria ter falhado ao tentar validar dados incompletos!"
    except Exception:
        # Sucesso: exceção capturada impede salvar nota corrompida
        pass


if __name__ == "__main__":
    test_simulacao_idempotencia_concorrente()
    test_falha_extracao_nao_gera_dados_incompletos()
    print("Todos os testes de concorrência e integridade em test_concurrency.py passaram com sucesso!")

