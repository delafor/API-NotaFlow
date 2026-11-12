import datetime
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from collaborative.consolidation_service import (
    AVISO_DADOS_LIMITADOS,
    calcular_atualidade,
    calcular_indicador_confiabilidade,
    consolidar_precos_por_estabelecimento,
)
from collaborative.price_validator import (
    gerar_id_deterministico_contribuicao,
    gerar_identificador_anonimo_contribuicao,
    validar_preco_comercial,
)
from collaborative.regional_service import (
    identificar_regiao,
    obter_cidades_abrangencia,
)


def test_cenario_objetivo_principal_tres_usuarios_arroz_5kg():
    """
    Valida o cenário exato da Seção 2 e Seção 3 da especificação:
    - Usuário A compra arroz 5kg no Mercado X por R$ 29,90 (hoje)
    - Usuário B compra arroz 5kg no Mercado Y por R$ 25,90 (há 2 dias)
    - Usuário C compra arroz 5kg no Mercado Z por R$ 27,50 (ontem)
    """
    agora = datetime.datetime(2026, 11, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)

    registros = [
        {
            "estabelecimento_id": "est_mercado_x",
            "nome_estabelecimento": "MERCADO X",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "preco": 29.90,
            "preco_por_unidade": 5.98,
            "unidade_padrao": "KG",
            "condicao_preco": "NORMAL",
            "data_compra": agora,
            "atualizado_em": agora,
            "status_validacao": "APROVADO",
            "identificador_anonimo_de_contribuicao": gerar_identificador_anonimo_contribuicao("uid_user_a"),
        },
        {
            "estabelecimento_id": "est_mercado_y",
            "nome_estabelecimento": "MERCADO Y",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "preco": 25.90,
            "preco_por_unidade": 5.18,
            "unidade_padrao": "KG",
            "condicao_preco": "NORMAL",
            "data_compra": agora - datetime.timedelta(days=2),
            "atualizado_em": agora - datetime.timedelta(days=2),
            "status_validacao": "APROVADO",
            "identificador_anonimo_de_contribuicao": gerar_identificador_anonimo_contribuicao("uid_user_b"),
        },
        {
            "estabelecimento_id": "est_mercado_z",
            "nome_estabelecimento": "MERCADO Z",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "preco": 27.50,
            "preco_por_unidade": 5.50,
            "unidade_padrao": "KG",
            "condicao_preco": "NORMAL",
            "data_compra": agora - datetime.timedelta(days=1),
            "atualizado_em": agora - datetime.timedelta(days=1),
            "status_validacao": "APROVADO",
            "identificador_anonimo_de_contribuicao": gerar_identificador_anonimo_contribuicao("uid_user_c"),
        },
    ]

    estabs, qtd_usuarios, qtd_regs, _ = consolidar_precos_por_estabelecimento(
        registros=registros,
        referencia_utc=agora,
    )

    assert len(estabs) == 3
    assert qtd_usuarios == 3
    assert qtd_regs == 3

    # Ordenação por menor preço: MERCADO Y (25.90), MERCADO Z (27.50), MERCADO X (29.90)
    assert estabs[0].nome_estabelecimento == "MERCADO Y"
    assert estabs[0].preco == 25.90
    assert estabs[0].rotulo_tempo == "Comprado há 2 dias"
    assert estabs[0].eh_menor_preco is True
    assert estabs[0].diferenca_reais == 0.0

    assert estabs[1].nome_estabelecimento == "MERCADO Z"
    assert estabs[1].preco == 27.50
    assert estabs[1].rotulo_tempo == "Comprado ontem"
    assert estabs[1].diferenca_reais == 1.60

    assert estabs[2].nome_estabelecimento == "MERCADO X"
    assert estabs[2].preco == 29.90
    assert estabs[2].rotulo_tempo == "Comprado hoje"
    assert estabs[2].diferenca_reais == 4.00

    conf = calcular_indicador_confiabilidade(
        quantidade_usuarios_distintos=qtd_usuarios,
        quantidade_registros_validos=qtd_regs,
        status_atualidade_melhor=estabs[0].status_atualidade,
        tem_gtin_ou_exata=True,
    )
    assert conf.nivel == "ALTA"
    assert conf.dados_limitados is False
    assert conf.aviso_dados_limitados is None


def test_aviso_dados_limitados_quando_menos_de_tres_usuarios():
    conf_1_usuario = calcular_indicador_confiabilidade(
        quantidade_usuarios_distintos=1,
        quantidade_registros_validos=1,
        status_atualidade_melhor="RECENTE",
        tem_gtin_ou_exata=True,
    )
    assert conf_1_usuario.dados_limitados is True
    assert conf_1_usuario.aviso_dados_limitados == AVISO_DADOS_LIMITADOS

    conf_2_usuarios = calcular_indicador_confiabilidade(
        quantidade_usuarios_distintos=2,
        quantidade_registros_validos=2,
        status_atualidade_melhor="RECENTE",
        tem_gtin_ou_exata=True,
    )
    assert conf_2_usuarios.dados_limitados is True
    assert conf_2_usuarios.aviso_dados_limitados == AVISO_DADOS_LIMITADOS


def test_regras_atualidade_datas_e_exclusao_desatualizados():
    agora = datetime.datetime(2026, 11, 5, 12, 0, 0, tzinfo=datetime.timezone.utc)

    _, _, st_recente = calcular_atualidade(agora - datetime.timedelta(days=5), agora)
    _, _, st_atencao = calcular_atualidade(agora - datetime.timedelta(days=15), agora)
    _, _, st_desatualizado = calcular_atualidade(agora - datetime.timedelta(days=45), agora)

    assert st_recente == "RECENTE"
    assert st_atencao == "ATENCAO"
    assert st_desatualizado == "DESATUALIZADO"

    # Preços com mais de 30 dias não devem aparecer como preços atuais
    regs = [
        {
            "estabelecimento_id": "est_antigo",
            "nome_estabelecimento": "MERCADO ANTIGO",
            "cidade_id": "2928901",
            "uf": "BA",
            "preco": 15.00,
            "data_compra": agora - datetime.timedelta(days=40),
            "status_validacao": "APROVADO",
            "identificador_anonimo_de_contribuicao": "anon_1",
        }
    ]
    estabs, _, _, _ = consolidar_precos_por_estabelecimento(regs, referencia_utc=agora)
    assert len(estabs) == 0


def test_validacao_precos_e_outliers():
    st_zero, _ = validar_preco_comercial(0.0)
    assert st_zero == "REJEITADO"

    st_neg, _ = validar_preco_comercial(-10.0)
    assert st_neg == "REJEITADO"

    historico = [25.90, 26.50, 27.90, 28.00]
    st_ok, _ = validar_preco_comercial(24.90, historico)
    assert st_ok == "APROVADO"

    st_outlier_baixo, _ = validar_preco_comercial(1.50, historico)
    assert st_outlier_baixo == "QUARENTENA_OUTLIER"

    st_outlier_alto, _ = validar_preco_comercial(150.00, historico)
    assert st_outlier_alto == "QUARENTENA_OUTLIER"


def test_filtros_regionais_e_abrangencia_30km():
    regiao_santa_ines = identificar_regiao(municipio="Santa Inês", uf="BA")
    assert regiao_santa_ines["cidade_id"] == "2928901"

    # Apenas minha cidade
    cidades_local, _ = obter_cidades_abrangencia(regiao_santa_ines, abrangencia="apenas_cidade")
    assert "2928901" in cidades_local
    assert "2917607" not in cidades_local  # Jaguaquara não entra em 'apenas_cidade'

    # Minha cidade e municípios próximos (até 35 km: Cravolândia ~7km, Ubaíra ~17km, Jaguaquara ~31km)
    cidades_proximas, dists = obter_cidades_abrangencia(
        regiao_santa_ines,
        abrangencia="cidade_e_proximos",
        raio_km=35,
    )
    assert "2928901" in cidades_proximas
    assert "2908903" in cidades_proximas  # Cravolândia
    assert "2932002" in cidades_proximas  # Ubaíra
    assert "2927408" not in cidades_proximas  # Salvador (> 140km) não entra


def test_desempenho_consolidacao_grande_volume():
    """Verifica latência de consolidação com 1.000 registros simultâneos."""
    agora = datetime.datetime.now(datetime.timezone.utc)
    registros_volume = [
        {
            "estabelecimento_id": f"est_{i % 20}",
            "nome_estabelecimento": f"Mercado {i % 20}",
            "cidade_id": "2928901",
            "nome_cidade": "Santa Inês",
            "uf": "BA",
            "preco": 20.0 + (i % 10) * 0.5,
            "preco_por_unidade": 4.0 + (i % 10) * 0.1,
            "unidade_padrao": "KG",
            "condicao_preco": "NORMAL",
            "data_compra": agora - datetime.timedelta(days=i % 6),
            "atualizado_em": agora,
            "status_validacao": "APROVADO",
            "identificador_anonimo_de_contribuicao": f"anon_user_{i % 50}",
        }
        for i in range(1000)
    ]

    inicio = time.perf_counter()
    estabs, qtd_users, qtd_regs, _ = consolidar_precos_por_estabelecimento(
        registros_volume,
        referencia_utc=agora,
    )
    duracao_ms = (time.perf_counter() - inicio) * 1000.0

    assert len(estabs) == 20
    assert qtd_users == 50
    assert qtd_regs == 1000
    assert duracao_ms < 150.0  # Consolidação de 1.000 registros em menos de 150ms

