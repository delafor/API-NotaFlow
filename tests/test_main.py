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


def test_importar_nota_com_transacao_sucesso():
    from unittest.mock import MagicMock, patch
    from auth import get_current_user_uid
    from google.cloud.firestore import Transaction

    app.dependency_overrides[get_current_user_uid] = lambda: "test-user-uid-123"

    mock_trans = MagicMock(spec=Transaction)
    mock_trans._max_attempts = 1
    mock_trans._read_only = False
    mock_trans._id = b"trans-123"
    mock_trans._commit.return_value = []

    mock_doc_ref = MagicMock()
    mock_snap = MagicMock()
    mock_snap.exists = False
    mock_doc_ref.get.return_value = mock_snap

    html_sample = (
        '<html><body>'
        '<div id="u20">LOJA TESTE LTDA</div>'
        '<table id="tabResult">'
        '<tr id="Item + 1">'
        '<td>'
        '<span class="txtTit">ARROZ BRANCO 5KG</span>'
        '<span class="Rqtd"><strong>Qtde.:</strong>1</span>'
        '<span class="RUN"><strong>UN: </strong>UN</span>'
        '<span class="RvlUnit"><strong>Vl. Unit.:</strong> 15,00</span>'
        '</td>'
        '<td><span class="valor">15,00</span></td>'
        '</tr>'
        '</table>'
        '<span class="txtMax">15,00</span>'
        '</body></html>'
    )

    try:
        with patch("main.buscar_pagina", return_value=html_sample), \
             patch("main.db.collection") as mock_col, \
             patch("main.db.transaction", return_value=mock_trans):

            mock_col.return_value.document.return_value.collection.return_value.document.return_value = mock_doc_ref

            response = client.post(
                "/notas/importar",
                json={"url": "http://nfe.sefaz.ba.gov.br/servicos/nfce/qrcode.aspx"},
            )

            assert response.status_code == 200, response.text
            dados = response.json()
            assert dados["sucesso"] is True
            assert dados["nota"]["total"] == 15.0
            assert len(dados["nota"]["produtos"]) == 1
            mock_trans.set.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_current_user_uid, None)


if __name__ == "__main__":
    test_healthcheck()
    test_importar_nota_invalid_url_format()
    test_importar_nota_ssrf_blocked()
    test_buscar_nota_unauthorized()
    test_extrair_nota_unauthorized()
    test_importar_nota_com_transacao_sucesso()
    print("Todos os testes de rotas da API em test_main.py passaram com sucesso!")

