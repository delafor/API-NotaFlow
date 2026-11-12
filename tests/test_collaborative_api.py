import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from auth import get_current_user_uid
from main import app

client = TestClient(app)


def test_endpoints_colaborativos_exigem_autenticacao():
    """Garante que todas as rotas colaborativas rejeitam acesso não autenticado com 401."""
    app.dependency_overrides.clear()

    assert client.get("/precos-colaborativos/pesquisa?q=arroz").status_code == 401
    assert client.get("/precos-colaborativos/produto/prod_arroz").status_code == 401
    assert client.get("/precos-colaborativos/produto/prod_arroz/historico").status_code == 401
    assert client.get("/precos-colaborativos/regiao").status_code == 401
    assert client.get("/precos-colaborativos/estabelecimentos/est_1").status_code == 401
    assert client.post("/precos-colaborativos/processar-nota/nota_1").status_code == 401
    assert client.patch(
        "/usuarios/preferencias/compartilhamento",
        json={"compartilhamento_ativo": True},
    ).status_code == 401


def test_pesquisa_e_comparacao_sem_expor_dados_pessoais():
    """
    Verifica que os endpoints autenticados retornam apenas dados comerciais agregados,
    jamais expondo UID, e-mail ou identificadores individuais de terceiros.
    """
    app.dependency_overrides[get_current_user_uid] = lambda: "uid_teste_seguro_123"

    registros_mock = [
        {
            "registro_id": "reg_1",
            "produto_id": "prod_arroz__tipo_1__camil__5kg",
            "nome_produto_normalizado": "ARROZ TIPO 1 CAMIL 5KG",
            "nome_exibicao": "Arroz — Tipo 1 — Marca Camil — 5 kg",
            "marca_nome": "Camil",
            "categoria_id": "mercearia_graos",
            "quantidade": 5.0,
            "unidade_medida": "KG",
            "unidade_padrao": "KG",
            "preco": 25.90,
            "preco_por_unidade": 5.18,
            "condicao_preco": "NORMAL",
            "estabelecimento_id": "est_mercado_y",
            "nome_estabelecimento": "Mercado Y",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "regiao_id": "ba_vale_jiquirica",
            "data_compra": "2026-11-04T10:00:00+00:00",
            "atualizado_em": "2026-11-04T10:00:00+00:00",
            "status_validacao": "APROVADO",
            "tokens_busca": ["arroz", "tipo", "camil", "5kg"],
            "identificador_anonimo_de_contribuicao": "anon_a1b2c3d4",
        },
        {
            "registro_id": "reg_2",
            "produto_id": "prod_arroz__tipo_1__camil__5kg",
            "nome_produto_normalizado": "ARROZ TIPO 1 CAMIL 5KG",
            "nome_exibicao": "Arroz — Tipo 1 — Marca Camil — 5 kg",
            "marca_nome": "Camil",
            "categoria_id": "mercearia_graos",
            "quantidade": 5.0,
            "unidade_medida": "KG",
            "unidade_padrao": "KG",
            "preco": 29.90,
            "preco_por_unidade": 5.98,
            "condicao_preco": "NORMAL",
            "estabelecimento_id": "est_mercado_x",
            "nome_estabelecimento": "Mercado X",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "regiao_id": "ba_vale_jiquirica",
            "data_compra": "2026-11-05T10:00:00+00:00",
            "atualizado_em": "2026-11-05T10:00:00+00:00",
            "status_validacao": "APROVADO",
            "tokens_busca": ["arroz", "tipo", "camil", "5kg"],
            "identificador_anonimo_de_contribuicao": "anon_e5f6g7h8",
        },
    ]

    prefs_mock = {
        "compartilhamento_ativo": True,
        "cidade_id": "2928901",
        "municipio": "Santa Inês",
        "uf": "BA",
        "codigo_ibge": "2928901",
        "regiao_id": "ba_vale_jiquirica",
        "nome_regiao": "Vale do Jiquiriçá - BA",
        "abrangencia": "cidade_e_proximos",
        "raio_km": 30,
        "lat": -13.2922,
        "lon": -39.8189,
    }

    with (
        patch("collaborative.repository.obter_preferencias_usuario", return_value=prefs_mock),
        patch("collaborative.repository._buscar_registros_firestore_regiao", return_value=registros_mock),
    ):
        resp = client.get("/precos-colaborativos/produto/prod_arroz__tipo_1__camil__5kg")
        assert resp.status_code == 200
        body = resp.json()
        raw_text = resp.text

        assert body["menor_preco"] == 25.90
        assert body["maior_preco"] == 29.90
        assert body["estabelecimento_mais_barato"] == "Mercado Y"
        assert body["economia_maxima_reais"] == 4.00
        assert body["total_usuarios_contribuintes"] == 2
        assert body["confiabilidade"]["dados_limitados"] is True
        assert body["confiabilidade"]["aviso_dados_limitados"] == "Dados colaborativos limitados nesta região."

        # Garante que nenhum identificador de contribuidor ou UID vaze no JSON de resposta
        assert "uid_teste_seguro_123" not in raw_text
        assert "anon_a1b2c3d4" not in raw_text
        assert "identificador_anonimo_de_contribuicao" not in raw_text

    app.dependency_overrides.clear()


def test_atualizar_preferencias_compartilhamento():
    app.dependency_overrides[get_current_user_uid] = lambda: "uid_user_prefs"

    with patch("collaborative.router.salvar_preferencias_usuario") as mock_save:
        mock_save.return_value = {
            "compartilhamento_ativo": False,
            "cidade_id": "2927408",
            "municipio": "Salvador",
            "uf": "BA",
            "codigo_ibge": "2927408",
            "regiao_id": "ba_metropolitana_salvador",
            "abrangencia": "apenas_cidade",
            "raio_km": 20,
            "atualizado_em": "2026-11-05T12:00:00+00:00",
        }
        resp = client.patch(
            "/usuarios/preferencias/compartilhamento",
            json={
                "compartilhamento_ativo": False,
                "municipio": "Salvador",
                "uf": "BA",
                "abrangencia": "apenas_cidade",
                "raio_km": 20,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["compartilhamento_ativo"] is False
        assert data["municipio"] == "Salvador"
        assert data["abrangencia"] == "apenas_cidade"

    app.dependency_overrides.clear()


def test_regras_seguranca_firestore_protegem_base_colaborativa_e_auditoria():
    base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    rules_path = os.path.join(base_dir, "firestore.rules")
    with open(rules_path, "r", encoding="utf-8") as f:
        conteudo = f.read()

    assert "match /precos_colaborativos/{registroId}" in conteudo
    assert "match /auditoria_contribuicoes/{notaHash}" in conteudo
    assert "allow read, write: if false;" in conteudo

