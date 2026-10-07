import os
import sys

# Garante que a raiz do projeto esteja no sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_home_endpoint_public():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"mensagem": "NotaFlow API funcionando!"}


def test_protected_endpoints_require_auth():
    # Attempting to fetch a note without Bearer token must return HTTP 401
    response = client.get("/notas/nota123")
    assert response.status_code == 401
    assert "detail" in response.json()

    # Attempting to extract a note without Bearer token must return HTTP 401
    response = client.post("/notas/nota123/extrair")
    assert response.status_code == 401

    # Attempting to import a note without Bearer token must return HTTP 401
    response = client.post(
        "/notas/importar",
        json={"url": "https://dfe-portal.svrs.rs.gov.br/test"},
    )
    assert response.status_code == 401


if __name__ == "__main__":
    test_home_endpoint_public()
    test_protected_endpoints_require_auth()
    print("Todos os testes de autenticação em test_auth.py passaram com sucesso!")

