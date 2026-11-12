import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from auth import get_current_user_uid
from collaborative.regional_service import CATALOGO_MUNICIPIOS, obter_cidades_abrangencia
from collaborative.repository import (
    _buscar_registros_firestore_regiao,
    consultar_comparacao_produto,
    consultar_historico_produto,
    consultar_status_job,
    obter_preferencias_usuario,
    pesquisar_produtos_colaborativos,
    processar_nota_colaborativa,
    salvar_preferencias_usuario,
)
from collaborative.schemas import (
    AbrangenciaRegional,
    ComparacaoProdutoResponse,
    HistoricoProdutoResponse,
    PesquisaColaborativaResponse,
    PreferenciasCompartilhamentoRequest,
    PreferenciasCompartilhamentoResponse,
    ProcessamentoNotaResponse,
)
from firebase import db
from security import rate_limiter

logger = logging.getLogger("notaflow_collaborative_router")

router = APIRouter(tags=["Comparação Colaborativa de Preços"])


def _verificar_rate_limit(request: Request, uid: str):
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"collab:{uid}:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de consultas colaborativas excedido. Aguarde alguns segundos.",
        )


@router.get(
    "/precos-colaborativos/pesquisa",
    response_model=PesquisaColaborativaResponse,
    summary="Pesquisa produtos e compara preços na região do usuário",
)
def endpoint_pesquisar_precos(
    request: Request,
    q: str = Query(default="", max_length=120, description="Termo de busca do produto ou código de barras"),
    municipio: Optional[str] = Query(default=None, max_length=100),
    uf: Optional[str] = Query(default=None, max_length=2),
    abrangencia: Optional[AbrangenciaRegional] = Query(default=None),
    raio_km: Optional[int] = Query(default=None, ge=5, le=150),
    estabelecimento: Optional[str] = Query(default=None, max_length=120),
    ordenar_por: str = Query(default="menor_preco", pattern="^(menor_preco|maior_economia)$"),
    limite: int = Query(default=25, ge=1, le=50),
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    return pesquisar_produtos_colaborativos(
        uid=uid,
        termo=q,
        municipio=municipio,
        uf=uf,
        abrangencia=abrangencia,
        raio_km=raio_km,
        estabelecimento_filtro=estabelecimento,
        ordenar_por=ordenar_por,
        limite=limite,
    )


@router.get(
    "/precos-colaborativos/produto/{produto_id}",
    response_model=ComparacaoProdutoResponse,
    summary="Consulta preços consolidados de um produto na região do usuário",
)
def endpoint_comparar_produto(
    produto_id: str,
    request: Request,
    municipio: Optional[str] = Query(default=None, max_length=100),
    uf: Optional[str] = Query(default=None, max_length=2),
    abrangencia: Optional[AbrangenciaRegional] = Query(default=None),
    raio_km: Optional[int] = Query(default=None, ge=5, le=150),
    estabelecimento: Optional[str] = Query(default=None, max_length=120),
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    if len(produto_id) > 128:
        raise HTTPException(status_code=400, detail="Identificador de produto inválido.")

    return consultar_comparacao_produto(
        uid=uid,
        produto_id=produto_id,
        municipio=municipio,
        uf=uf,
        abrangencia=abrangencia,
        raio_km=raio_km,
        estabelecimento_filtro=estabelecimento,
    )


@router.get(
    "/precos-colaborativos/produto/{produto_id}/historico",
    response_model=HistoricoProdutoResponse,
    summary="Retorna a evolução histórica dos preços do produto na região",
)
def endpoint_historico_produto(
    produto_id: str,
    request: Request,
    periodo_dias: int = Query(default=90, ge=7, le=365),
    municipio: Optional[str] = Query(default=None, max_length=100),
    uf: Optional[str] = Query(default=None, max_length=2),
    abrangencia: Optional[AbrangenciaRegional] = Query(default=None),
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    if len(produto_id) > 128:
        raise HTTPException(status_code=400, detail="Identificador de produto inválido.")

    return consultar_historico_produto(
        uid=uid,
        produto_id=produto_id,
        periodo_dias=periodo_dias,
        municipio=municipio,
        uf=uf,
        abrangencia=abrangencia,
    )


@router.get(
    "/precos-colaborativos/regiao",
    summary="Retorna os dados regionais e preferências colaborativas do usuário",
)
def endpoint_dados_regiao(
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    prefs = obter_preferencias_usuario(uid)
    cidades_ids, distancias = obter_cidades_abrangencia(
        regiao_base={
            "cidade_id": prefs["cidade_id"],
            "nome_cidade": prefs["municipio"],
            "uf": prefs["uf"],
            "regiao_id": prefs["regiao_id"],
            "lat": prefs.get("lat"),
            "lon": prefs.get("lon"),
        },
        abrangencia=prefs["abrangencia"],
        raio_km=prefs["raio_km"],
    )

    municipios_proximos = []
    for cid in cidades_ids:
        if cid in CATALOGO_MUNICIPIOS:
            cat = CATALOGO_MUNICIPIOS[cid]
            municipios_proximos.append(
                {
                    "cidade_id": cid,
                    "municipio": cat["nome"],
                    "uf": cat["uf"],
                    "distancia_km": distancias.get(cid, 0.0),
                }
            )

    municipios_catalogo = [
        {
            "codigo_ibge": v["codigo_ibge"],
            "municipio": v["nome"],
            "uf": v["uf"],
            "regiao_id": v["regiao_id"],
            "nome_regiao": v["nome_regiao"],
        }
        for v in CATALOGO_MUNICIPIOS.values()
    ]

    return {
        "compartilhamento_ativo": prefs["compartilhamento_ativo"],
        "cidade_id": prefs["cidade_id"],
        "municipio": prefs["municipio"],
        "uf": prefs["uf"],
        "codigo_ibge": prefs.get("codigo_ibge"),
        "regiao_id": prefs["regiao_id"],
        "nome_regiao": prefs.get("nome_regiao"),
        "abrangencia": prefs["abrangencia"],
        "raio_km": prefs["raio_km"],
        "municipios_abrangidos": municipios_proximos,
        "municipios_disponiveis": municipios_catalogo,
    }


@router.get(
    "/precos-colaborativos/estabelecimentos/{estabelecimento_id}",
    summary="Retorna informações comerciais e preços recentes do estabelecimento",
)
def endpoint_detalhes_estabelecimento(
    estabelecimento_id: str,
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    if len(estabelecimento_id) > 128:
        raise HTTPException(status_code=400, detail="Identificador de estabelecimento inválido.")

    prefs = obter_preferencias_usuario(uid)
    dados_estab = {}
    try:
        doc = db.collection("estabelecimentos").document(estabelecimento_id).get()
        if doc.exists:
            dados_estab = doc.to_dict() or {}
    except Exception:
        pass

    registros = _buscar_registros_firestore_regiao(
        cidades_elegiveis=[],
        uf=dados_estab.get("uf") or prefs["uf"],
        estabelecimento_id=estabelecimento_id,
        limite=50,
    )

    if not dados_estab and not registros:
        raise HTTPException(status_code=404, detail="Estabelecimento comercial não encontrado.")

    nome_est = dados_estab.get("nome_exibicao") or (
        registros[0].get("nome_estabelecimento") if registros else "Estabelecimento"
    )
    cidade_est = dados_estab.get("nome_cidade") or (
        registros[0].get("nome_cidade") if registros else prefs["municipio"]
    )
    uf_est = dados_estab.get("uf") or (registros[0].get("uf") if registros else prefs["uf"])

    produtos_recentes = []
    vistos = set()
    for r in registros:
        pid = r.get("produto_id")
        if not pid or pid in vistos:
            continue
        vistos.add(pid)
        produtos_recentes.append(
            {
                "produto_id": pid,
                "nome_produto": r.get("nome_exibicao") or r.get("nome_produto_normalizado"),
                "preco": r.get("preco"),
                "unidade_medida": r.get("unidade_medida", "UN"),
                "condicao_preco": r.get("condicao_preco", "NORMAL"),
            }
        )

    return {
        "estabelecimento_id": estabelecimento_id,
        "nome_estabelecimento": nome_est,
        "endereco_comercial": dados_estab.get("endereco_comercial"),
        "municipio": cidade_est,
        "uf": uf_est,
        "total_produtos_registrados": len(produtos_recentes),
        "produtos_recentes": produtos_recentes[:30],
    }


@router.post(
    "/precos-colaborativos/processar-nota/{nota_id}",
    response_model=ProcessamentoNotaResponse,
    summary="Processa de maneira idempotente os produtos de uma nota para a base colaborativa",
)
def endpoint_processar_nota(
    nota_id: str,
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    if len(nota_id) > 128:
        raise HTTPException(status_code=400, detail="Identificador de nota inválido.")

    try:
        return processar_nota_colaborativa(uid=uid, nota_id=nota_id)
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro ao processar nota colaborativa {nota_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao processar os dados comerciais da nota fiscal.",
        )


@router.get(
    "/precos-colaborativos/status/{job_id}",
    summary="Consulta o status de um processamento assíncrono colaborativo",
)
def endpoint_status_job(
    job_id: str,
    uid: str = Depends(get_current_user_uid),
):
    dados = consultar_status_job(job_id)
    if not dados:
        raise HTTPException(status_code=404, detail="Job de processamento não encontrado ou expirado.")
    return dados


@router.patch(
    "/usuarios/preferencias/compartilhamento",
    response_model=PreferenciasCompartilhamentoResponse,
    summary="Atualiza a preferência de participação colaborativa e região de comparação",
)
def endpoint_atualizar_preferencias(
    payload: PreferenciasCompartilhamentoRequest,
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    _verificar_rate_limit(request, uid)
    prefs = salvar_preferencias_usuario(
        uid=uid,
        compartilhamento_ativo=payload.compartilhamento_ativo,
        municipio=payload.municipio,
        uf=payload.uf,
        codigo_ibge=payload.codigo_ibge,
        abrangencia=payload.abrangencia,
        raio_km=payload.raio_km,
    )
    return PreferenciasCompartilhamentoResponse(
        sucesso=True,
        compartilhamento_ativo=prefs["compartilhamento_ativo"],
        cidade_id=prefs["cidade_id"],
        municipio=prefs["municipio"],
        uf=prefs["uf"],
        codigo_ibge=prefs.get("codigo_ibge"),
        regiao_id=prefs["regiao_id"],
        abrangencia=prefs["abrangencia"],
        raio_km=prefs["raio_km"],
        atualizado_em=prefs["atualizado_em"],
    )

