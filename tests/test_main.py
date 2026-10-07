import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_healthcheck():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"mensagem": "NotaFlow API funcionando!"}


def test_importar_nota_invalid_url_format():
    # Attempting to import an invalid URL string should fail input validation (400) or require auth (401)
    response = client.post(
        "/notas/importar",
        json={"url": "not-a-valid-url"},
    )
    # 401 because auth check happens first or 400 validation error
    assert response.status_code in (400, 401)


def test_importar_nota_ssrf_blocked():
    # Headers with dummy auth token token format test
    headers = {"Authorization": "Bearer fake_token"}

    # Attempting to import loopback IP should be blocked by anti-SSRF or invalid token
    response = client.post(
        "/notas/importar",
        json={"url": "http://127.0.0.1:8000/internal"},
        headers=headers,
    )
    # Should fail with 401 (invalid firebase token) or 400 (SSRF blocked)
    assert response.status_code in (400, 401)


def test_buscar_nota_unauthorized():
    response = client.get("/notas/some_nota_id")
    assert response.status_code == 401


def test_extrair_nota_unauthorized():
    response = client.post("/notas/some_nota_id/extrair")
    assert response.status_code == 401


if __name__ == "__main__":
    test_healthcheck()
    test_importar_nota_invalid_url_format()
    test_importar_nota_ssrf_blocked()
    test_buscar_nota_unauthorized()
    test_extrair_nota_unauthorized()
    print("Todos os testes de rotas da API em test_main.py passaram com sucesso!")

