import datetime
import hashlib
import logging
import statistics
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from collaborative.consolidation_service import (
    calcular_atualidade,
    calcular_indicador_confiabilidade,
    consolidar_precos_por_estabelecimento,
    construir_historico_evolucao,
)
from collaborative.establishment_resolver import resolver_estabelecimento
from collaborative.normalizer import (
    avaliar_correspondencia_produtos,
    normalizar_produto,
    remover_acentos,
)
from collaborative.price_validator import (
    classificar_condicao_preco,
    gerar_id_deterministico_contribuicao,
    gerar_identificador_anonimo_contribuicao,
    parse_data_compra,
    validar_preco_comercial,
)
from collaborative.regional_service import (
    CATALOGO_MUNICIPIOS,
    identificar_regiao,
    obter_cidades_abrangencia,
)
from collaborative.schemas import (
    ComparacaoProdutoResponse,
    HistoricoProdutoResponse,
    PesquisaColaborativaResponse,
    ProcessamentoNotaResponse,
    ResumoProdutoPesquisaSchema,
)
from firebase import db

logger = logging.getLogger("notaflow_collaborative")

# Cache em memória leve com TTL para reduzir leituras repetidas no Firestore
_CACHE_TTL_SECONDS = 120.0
_PREFS_CACHE_TTL_SECONDS = 60.0
_QUERY_CACHE: Dict[str, Tuple[float, Any]] = {}
_USER_PREFS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_JOBS_STATUS: Dict[str, Dict[str, Any]] = {}


def invalidar_cache_regiao(uf: Optional[str] = None):
    if not uf:
        _QUERY_CACHE.clear()
        _USER_PREFS_CACHE.clear()
        return
    uf_upper = uf.upper()
    chaves_remover = [k for k in _QUERY_CACHE.keys() if f":{uf_upper}:" in k]
    for k in chaves_remover:
        _QUERY_CACHE.pop(k, None)


def _obter_cache(chave: str) -> Optional[Any]:
    item = _QUERY_CACHE.get(chave)
    if not item:
        return None
    expira_em, valor = item
    if time.time() > expira_em:
        _QUERY_CACHE.pop(chave, None)
        return None
    return valor


def _salvar_cache(chave: str, valor: Any, ttl: float = _CACHE_TTL_SECONDS):
    if len(_QUERY_CACHE) > 500:
        # Evita crescimento ilimitado de memória
        chaves_antigas = list(_QUERY_CACHE.keys())[:100]
        for k in chaves_antigas:
            _QUERY_CACHE.pop(k, None)
    _QUERY_CACHE[chave] = (time.time() + ttl, valor)


def registrar_status_job(job_id: str, dados: Dict[str, Any]):
    if len(_JOBS_STATUS) > 300:
        antigos = list(_JOBS_STATUS.keys())[:50]
        for k in antigos:
            _JOBS_STATUS.pop(k, None)
    _JOBS_STATUS[job_id] = {
        **dados,
        "atualizado_em": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def consultar_status_job(job_id: str) -> Optional[Dict[str, Any]]:
    return _JOBS_STATUS.get(job_id)


def obter_preferencias_usuario(uid: str) -> Dict[str, Any]:
    """
    Obtém as preferências regionais e de compartilhamento colaborativo do usuário.
    Se o usuário ainda não configurou manualmente sua cidade, infere automaticamente
    a partir do município/UF de suas notas fiscais mais recentes (limit=5).
    """
    agora = time.time()
    em_cache = _USER_PREFS_CACHE.get(uid)
    if em_cache is not None:
        expira_em, prefs_cached = em_cache
        if agora <= expira_em:
            return prefs_cached.copy()
        _USER_PREFS_CACHE.pop(uid, None)

    try:
        user_ref = db.collection("usuarios").document(uid)
        user_doc = user_ref.get()
        dados_user = user_doc.to_dict() if user_doc.exists else {}
    except Exception:
        dados_user = {}

    prefs = (dados_user or {}).get("preferencias_colaborativas") or {}
    compartilhamento_ativo = prefs.get("compartilhamento_ativo", True)
    abrangencia = prefs.get("abrangencia", "cidade_e_proximos")
    raio_km = int(prefs.get("raio_km", 30))

    municipio = prefs.get("municipio")
    uf = prefs.get("uf")
    codigo_ibge = prefs.get("codigo_ibge")

    # Inferência automática a partir das últimas notas do próprio usuário se ainda não configurado
    if not municipio or not uf:
        try:
            notas_snap = (
                db.collection("usuarios")
                .document(uid)
                .collection("notas")
                .limit(5)
                .get()
            )
            for doc in notas_snap:
                d = doc.to_dict() or {}
                ext = d.get("dadosExtraidos") or {}
                mun_nota = ext.get("municipio") or ext.get("origem")
                uf_nota = ext.get("uf")
                ibge_nota = ext.get("codigo_ibge")
                chave_nota = ext.get("chave") or d.get("chave")
                end_nota = ext.get("endereco")
                if mun_nota or ibge_nota or chave_nota or end_nota:
                    reg_detectada = identificar_regiao(
                        municipio=mun_nota,
                        uf=uf_nota,
                        codigo_ibge=ibge_nota,
                        chave_nota=chave_nota,
                        endereco_nota=end_nota,
                    )
                    municipio = reg_detectada["nome_cidade"]
                    uf = reg_detectada["uf"]
                    codigo_ibge = reg_detectada.get("codigo_ibge")
                    break
        except Exception:
            pass

    regiao = identificar_regiao(
        municipio=municipio,
        uf=uf,
        codigo_ibge=codigo_ibge,
    )

    resultado = {
        "compartilhamento_ativo": bool(compartilhamento_ativo),
        "cidade_id": regiao["cidade_id"],
        "municipio": regiao["nome_cidade"],
        "uf": regiao["uf"],
        "codigo_ibge": regiao.get("codigo_ibge"),
        "regiao_id": regiao["regiao_id"],
        "nome_regiao": regiao.get("nome_regiao", regiao["regiao_id"]),
        "abrangencia": abrangencia,
        "raio_km": raio_km,
        "lat": regiao.get("lat"),
        "lon": regiao.get("lon"),
    }
    if len(_USER_PREFS_CACHE) > 500:
        _USER_PREFS_CACHE.clear()
    _USER_PREFS_CACHE[uid] = (agora + _PREFS_CACHE_TTL_SECONDS, resultado)
    return resultado.copy()


def salvar_preferencias_usuario(
    uid: str,
    compartilhamento_ativo: bool,
    municipio: Optional[str] = None,
    uf: Optional[str] = None,
    codigo_ibge: Optional[str] = None,
    abrangencia: str = "cidade_e_proximos",
    raio_km: int = 30,
) -> Dict[str, Any]:
    _USER_PREFS_CACHE.pop(uid, None)
    atuais = obter_preferencias_usuario(uid)
    regiao = identificar_regiao(
        municipio=municipio or atuais["municipio"],
        uf=uf or atuais["uf"],
        codigo_ibge=codigo_ibge or atuais.get("codigo_ibge"),
    )
    agora_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

    novas_prefs = {
        "compartilhamento_ativo": bool(compartilhamento_ativo),
        "cidade_id": regiao["cidade_id"],
        "municipio": regiao["nome_cidade"],
        "uf": regiao["uf"],
        "codigo_ibge": regiao.get("codigo_ibge"),
        "regiao_id": regiao["regiao_id"],
        "abrangencia": abrangencia,
        "raio_km": int(raio_km),
        "atualizado_em": agora_iso,
    }

    try:
        db.collection("usuarios").document(uid).set(
            {"preferencias_colaborativas": novas_prefs},
            merge=True,
        )
    except Exception as e:
        logger.warning(f"Falha ao persistir preferências no Firestore para uid={uid}: {e}")

    _USER_PREFS_CACHE.pop(uid, None)
    return novas_prefs


def _extrair_itens_comerciais_da_nota(dados_extraidos: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extrai os itens comerciais padronizados de uma NFC-e (produtos) ou BP-e (passagem).
    """
    tipo = (dados_extraidos.get("tipo") or "NFC-e").upper()
    itens_brutos = []

    if "BP-E" in tipo or "BPE" in tipo:
        destino = dados_extraidos.get("destino")
        origem = dados_extraidos.get("origem")
        preco = (
            dados_extraidos.get("valor_pagar")
            or dados_extraidos.get("total")
            or dados_extraidos.get("tarifa")
            or 0.0
        )
        if destino and float(preco or 0) > 0:
            dest_limpo = str(destino).replace("(BA)", "").strip()
            orig_limpo = str(origem or "").replace("(BA)", "").strip()
            nome_passagem = (
                f"PASSAGEM DE {orig_limpo} PARA {dest_limpo}"
                if orig_limpo
                else f"PASSAGEM PARA {dest_limpo}"
            )
            itens_brutos.append(
                {
                    "nome": nome_passagem,
                    "codigo": None,
                    "gtin": None,
                    "quantidade": 1.0,
                    "unidade": "UN",
                    "valor_unitario": float(preco),
                    "valor_total": float(preco),
                }
            )
        return itens_brutos

    produtos = dados_extraidos.get("produtos") or []
    for p in produtos:
        if not isinstance(p, dict):
            continue
        nome = p.get("nome")
        if not nome:
            continue
        qtd = float(p.get("quantidade") or 1.0)
        v_unit = p.get("valor_unitario")
        v_total = p.get("valor_total")
        if v_unit is None and v_total is not None and qtd > 0:
            v_unit = round(float(v_total) / qtd, 2)
        if v_unit is not None and float(v_unit) > 0:
            itens_brutos.append(
                {
                    "nome": str(nome),
                    "codigo": p.get("codigo"),
                    "gtin": p.get("gtin"),
                    "quantidade": qtd,
                    "unidade": str(p.get("unidade") or "UN"),
                    "valor_unitario": float(v_unit),
                    "valor_total": float(v_total or v_unit),
                }
            )
    return itens_brutos


def processar_nota_colaborativa(
    uid: str,
    nota_id: str,
    dados_nota_override: Optional[Dict[str, Any]] = None,
    job_id: Optional[str] = None,
) -> ProcessamentoNotaResponse:
    """
    Executa o pipeline completo e idempotente de processamento colaborativo de uma nota fiscal:
    1. Valida nota e propriedade do usuário.
    2. Verifica consentimento voluntário de compartilhamento (`compartilhamento_ativo`).
    3. Identifica região (Município, UF, IBGE) e estabelecimento (CNPJ/endereço/filial).
    4. Normaliza produtos, calcula R$/unidade e valida preços.
    5. Publica de forma idempotente em `precos_colaborativos`, `catalogo_produtos` e `estabelecimentos`.
    6. Registra auditoria privada em `auditoria_contribuicoes` sem expor dados pessoais na base colaborativa.
    """
    jid = job_id or f"job_{uuid.uuid4().hex[:12]}"

    # 1. Verifica consentimento do usuário
    prefs = obter_preferencias_usuario(uid)
    if not prefs.get("compartilhamento_ativo", True):
        resp = ProcessamentoNotaResponse(
            sucesso=True,
            job_id=jid,
            nota_id=nota_id,
            status="IGNORADO_OPT_OUT",
            itens_processados=0,
            itens_aprovados=0,
            itens_rejeitados_ou_quarentena=0,
            mensagem="Compartilhamento colaborativo desativado nas preferências do usuário.",
        )
        registrar_status_job(jid, resp.model_dump())
        return resp

    # 2. Obtém dados da nota
    dados_doc = dados_nota_override
    if not dados_doc:
        doc_ref = (
            db.collection("usuarios")
            .document(uid)
            .collection("notas")
            .document(nota_id)
        )
        snap = doc_ref.get()
        if not snap.exists:
            raise ValueError("Nota fiscal não encontrada na conta do usuário autenticado.")
        dados_doc = snap.to_dict() or {}

    dados_extraidos = dados_doc.get("dadosExtraidos") if "dadosExtraidos" in dados_doc else dados_doc
    if not isinstance(dados_extraidos, dict) or not dados_extraidos:
        raise ValueError("A nota não possui dados fiscais estruturados para processamento colaborativo.")

    chave_nota = dados_extraidos.get("chave") or dados_doc.get("chave")
    identificador_unico_nota = str(chave_nota or nota_id).strip()
    nota_hash = hashlib.sha256(identificador_unico_nota.encode("utf-8")).hexdigest()[:32]

    # 3. Verificação de idempotência na coleção privada de auditoria
    try:
        audit_ref = db.collection("auditoria_contribuicoes").document(f"audit_{nota_hash}")
        audit_snap = audit_ref.get()
        if audit_snap.exists:
            audit_data = audit_snap.to_dict() or {}
            if audit_data.get("status") == "CONCLUIDO" and audit_data.get("itens_aprovados", 0) > 0:
                resp = ProcessamentoNotaResponse(
                    sucesso=True,
                    job_id=jid,
                    nota_id=nota_id,
                    status="IDEMPOTENTE",
                    itens_processados=audit_data.get("itens_processados", 0),
                    itens_aprovados=audit_data.get("itens_aprovados", 0),
                    itens_rejeitados_ou_quarentena=audit_data.get("itens_rejeitados", 0),
                    cidade_identificada=audit_data.get("cidade_id"),
                    uf_identificada=audit_data.get("uf"),
                    estabelecimento_id=audit_data.get("estabelecimento_id"),
                    mensagem="Nota fiscal já processada anteriormente (operação idempotente).",
                )
                registrar_status_job(jid, resp.model_dump())
                return resp
    except Exception:
        audit_ref = None

    # 4. Identificação Regional (Município, UF, IBGE)
    regiao = identificar_regiao(
        municipio=dados_extraidos.get("municipio") or prefs.get("municipio"),
        uf=dados_extraidos.get("uf") or prefs.get("uf"),
        codigo_ibge=dados_extraidos.get("codigo_ibge") or prefs.get("codigo_ibge"),
        chave_nota=chave_nota,
        endereco_nota=dados_extraidos.get("endereco"),
    )

    # 5. Identificação Padronizada do Estabelecimento
    nome_estab_bruto = dados_extraidos.get("estabelecimento") or dados_doc.get("titulo") or "Mercado"
    estab = resolver_estabelecimento(
        nome_bruto=nome_estab_bruto,
        cnpj_bruto=dados_extraidos.get("cnpj"),
        chave_nota=chave_nota,
        endereco_comercial=dados_extraidos.get("endereco"),
        cidade_id=regiao["cidade_id"],
        nome_cidade=regiao["nome_cidade"],
        uf=regiao["uf"],
    )

    # 6. Data real da compra e Identificador Anônimo do Contribuidor
    dt_compra = parse_data_compra(
        emissao_str=dados_extraidos.get("emissao") or dados_extraidos.get("data_hora"),
        data_str=dados_doc.get("data") or dados_extraidos.get("data"),
    )
    agora_utc = datetime.datetime.now(datetime.timezone.utc)
    anon_contributor_id = gerar_identificador_anonimo_contribuicao(uid)
    origem_doc = "bpe_sefaz" if dados_extraidos.get("tipo") == "BP-e" else "nfce_sefaz"

    itens_brutos = _extrair_itens_comerciais_da_nota(dados_extraidos)
    itens_aprovados = 0
    itens_rejeitados = 0

    try:
        batch = db.batch()
        operacoes_batch = 0

        # Registra/atualiza estabelecimento padronizado
        estab_ref = db.collection("estabelecimentos").document(estab["estabelecimento_id"])
        batch.set(
            estab_ref,
            {
                **estab,
                "regiao_id": regiao["regiao_id"],
                "atualizado_em": agora_utc,
            },
            merge=True,
        )
        operacoes_batch += 1

        for item in itens_brutos:
            try:
                norm = normalizar_produto(
                    nome_bruto=item["nome"],
                    unidade_nota=item["unidade"],
                    codigo_nota=item.get("codigo"),
                    gtin_extraido=item.get("gtin"),
                    preco_praticado=item["valor_unitario"],
                )
            except ValueError:
                itens_rejeitados += 1
                continue

            condicao = classificar_condicao_preco(
                quantidade_comprada=item["quantidade"],
                unidade_medida=norm["unidade_medida"],
                desconto_nota=dados_extraidos.get("desconto"),
                nome_bruto=item["nome"],
            )

            status_val, _ = validar_preco_comercial(item["valor_unitario"])
            if status_val == "REJEITADO":
                itens_rejeitados += 1
                continue

            registro_id = gerar_id_deterministico_contribuicao(
                identificador_nota=identificador_unico_nota,
                produto_id=norm["produto_id"],
                estabelecimento_id=estab["estabelecimento_id"],
            )

            doc_preco = {
                "registro_id": registro_id,
                "produto_id": norm["produto_id"],
                "chave_equivalente": norm["chave_equivalente"],
                "chave_familia_unidade": norm["chave_familia_unidade"],
                "nome_produto_normalizado": norm["nome_produto_normalizado"],
                "nome_exibicao": norm["nome_exibicao"],
                "item_base": norm["item_base"],
                "tipo_produto": norm["tipo_produto"],
                "marca_id": norm["marca_id"],
                "marca_nome": norm["marca_nome"],
                "categoria_id": norm["categoria_id"],
                "quantidade": norm["quantidade_embalagem"],
                "unidade_medida": norm["unidade_medida"],
                "unidade_padrao": norm["unidade_padrao"],
                "preco": round(item["valor_unitario"], 2),
                "preco_por_unidade": norm["preco_por_unidade"],
                "condicao_preco": condicao,
                "gtin": norm["gtin"],
                "tokens_busca": norm["tokens_busca"],
                "estabelecimento_id": estab["estabelecimento_id"],
                "nome_estabelecimento": estab["nome_exibicao"],
                "cidade_id": regiao["cidade_id"],
                "nome_cidade": regiao["nome_cidade"],
                "uf": regiao["uf"],
                "regiao_id": regiao["regiao_id"],
                "data_compra": dt_compra,
                "criado_em": agora_utc,
                "atualizado_em": agora_utc,
                "origem": origem_doc,
                "status_validacao": status_val,
                "identificador_anonimo_de_contribuicao": anon_contributor_id,
            }

            preco_ref = db.collection("precos_colaborativos").document(registro_id)
            batch.set(preco_ref, doc_preco, merge=True)
            operacoes_batch += 1

            # Atualiza catálogo normalizado de produtos
            prod_ref = db.collection("catalogo_produtos").document(norm["produto_id"])
            batch.set(
                prod_ref,
                {
                    "produto_id": norm["produto_id"],
                    "chave_equivalente": norm["chave_equivalente"],
                    "nome_exibicao": norm["nome_exibicao"],
                    "nome_produto_normalizado": norm["nome_produto_normalizado"],
                    "item_base": norm["item_base"],
                    "tipo_produto": norm["tipo_produto"],
                    "marca_id": norm["marca_id"],
                    "marca_nome": norm["marca_nome"],
                    "categoria_id": norm["categoria_id"],
                    "quantidade_embalagem": norm["quantidade_embalagem"],
                    "unidade_medida": norm["unidade_medida"],
                    "unidade_padrao": norm["unidade_padrao"],
                    "gtin": norm["gtin"],
                    "tokens_busca": norm["tokens_busca"],
                    "atualizado_em": agora_utc,
                },
                merge=True,
            )
            operacoes_batch += 1

            if status_val == "APROVADO":
                itens_aprovados += 1
            else:
                itens_rejeitados += 1

        # Registra auditoria privada (sem dados pessoais abertos na base pública)
        if audit_ref is not None:
            batch.set(
                audit_ref,
                {
                    "nota_hash": nota_hash,
                    "identificador_anonimo": anon_contributor_id,
                    "estabelecimento_id": estab["estabelecimento_id"],
                    "cidade_id": regiao["cidade_id"],
                    "uf": regiao["uf"],
                    "itens_processados": len(itens_brutos),
                    "itens_aprovados": itens_aprovados,
                    "itens_rejeitados": itens_rejeitados,
                    "status": "CONCLUIDO",
                    "processado_em": agora_utc,
                },
                merge=True,
            )
            operacoes_batch += 1

        if operacoes_batch > 0:
            batch.commit()

        invalidar_cache_regiao(regiao["uf"])
    except Exception as e:
        logger.error(f"Erro ao gravar lote colaborativo da nota {nota_id}: {e}", exc_info=True)
        raise

    resp = ProcessamentoNotaResponse(
        sucesso=True,
        job_id=jid,
        nota_id=nota_id,
        status="CONCLUIDO",
        itens_processados=len(itens_brutos),
        itens_aprovados=itens_aprovados,
        itens_rejeitados_ou_quarentena=itens_rejeitados,
        cidade_identificada=regiao["nome_cidade"],
        uf_identificada=regiao["uf"],
        estabelecimento_id=estab["estabelecimento_id"],
        mensagem=f"{itens_aprovados} produto(s) compartilhado(s) anonimamente na base regional ({regiao['nome_cidade']}/{regiao['uf']}).",
    )
    registrar_status_job(jid, resp.model_dump())
    return resp


def _buscar_registros_firestore_regiao(
    cidades_elegiveis: List[str],
    uf: str,
    produto_id: Optional[str] = None,
    token_busca: Optional[str] = None,
    estabelecimento_id: Optional[str] = None,
    limite: int = 120,
) -> List[Dict[str, Any]]:
    """
    Executa consulta filtrada no Firestore na coleção `precos_colaborativos`,
    evitando table scans globais e reaproveitando cache em memória por UF/filtro.
    """
    uf_upper = uf.upper()
    chave_raw = f"raw:{uf_upper}:{produto_id or ''}:{estabelecimento_id or ''}:{(token_busca or '').lower()}:{limite}"
    docs_em_cache = _obter_cache(chave_raw)

    if docs_em_cache is None:
        colecao = db.collection("precos_colaborativos")
        docs_em_cache = []
        try:
            query = colecao.where("uf", "==", uf_upper).where("status_validacao", "==", "APROVADO")
            if produto_id:
                query = query.where("produto_id", "==", produto_id)
            elif estabelecimento_id:
                query = query.where("estabelecimento_id", "==", estabelecimento_id)
            elif token_busca:
                query = query.where("tokens_busca", "array_contains", token_busca.lower())

            docs = query.limit(limite).get()
            for d in docs:
                item = d.to_dict() or {}
                if item:
                    docs_em_cache.append(item)
            _salvar_cache(chave_raw, docs_em_cache)
        except Exception as e:
            logger.warning(f"Erro em consulta filtrada a precos_colaborativos: {e}")

    if not cidades_elegiveis:
        return list(docs_em_cache)

    cidades_set = {c.lower() for c in cidades_elegiveis}
    return [
        item
        for item in docs_em_cache
        if str(item.get("cidade_id", "")).lower() in cidades_set
    ]


def consultar_comparacao_produto(
    uid: str,
    produto_id: str,
    municipio: Optional[str] = None,
    uf: Optional[str] = None,
    abrangencia: Optional[str] = None,
    raio_km: Optional[int] = None,
    estabelecimento_filtro: Optional[str] = None,
) -> ComparacaoProdutoResponse:
    """
    Retorna a comparação colaborativa consolidada para um `produto_id` na região autorizada do usuário.
    """
    prefs = obter_preferencias_usuario(uid) if (not municipio or not uf) else {}
    regiao = identificar_regiao(
        municipio=municipio or prefs.get("municipio"),
        uf=uf or prefs.get("uf"),
        codigo_ibge=prefs.get("codigo_ibge") if not municipio else None,
    )
    abr_efetiva = abrangencia or prefs.get("abrangencia", "cidade_e_proximos")
    raio_efetivo = int(raio_km or prefs.get("raio_km", 30))

    chave_cache = f"prod:{produto_id}:{regiao['uf']}:{regiao['cidade_id']}:{abr_efetiva}:{raio_efetivo}:{estabelecimento_filtro or ''}"
    em_cache = _obter_cache(chave_cache)
    if em_cache is not None:
        return em_cache

    cidades_elegiveis, distancias = obter_cidades_abrangencia(
        regiao_base=regiao,
        abrangencia=abr_efetiva,
        raio_km=raio_efetivo,
    )

    registros = _buscar_registros_firestore_regiao(
        cidades_elegiveis=cidades_elegiveis,
        uf=regiao["uf"],
        produto_id=produto_id,
        limite=150,
    )

    if estabelecimento_filtro:
        filtro_lower = estabelecimento_filtro.strip().lower()
        registros = [
            r for r in registros
            if filtro_lower in str(r.get("nome_estabelecimento", "")).lower()
            or filtro_lower == str(r.get("estabelecimento_id", "")).lower()
        ]

    estabelecimentos, total_usuarios, total_registros, ultima_iso = consolidar_precos_por_estabelecimento(
        registros=registros,
        distancias_cidades=distancias,
    )

    # Metadados do produto a partir do registro mais recente ou do catálogo
    meta = registros[0] if registros else {}
    if not meta:
        try:
            cat_doc = db.collection("catalogo_produtos").document(produto_id).get()
            if cat_doc.exists:
                meta = cat_doc.to_dict() or {}
        except Exception:
            pass

    nome_produto = meta.get("nome_exibicao") or meta.get("nome_produto_normalizado") or produto_id
    nome_norm = meta.get("nome_produto_normalizado") or nome_produto.upper()
    marca = meta.get("marca_nome")
    categoria = meta.get("categoria_id") or "mercearia_geral"
    qtd_emb = float(meta.get("quantidade") or meta.get("quantidade_embalagem") or 1.0)
    un_med = meta.get("unidade_medida") or "UN"
    un_pad = meta.get("unidade_padrao") or "UN"
    gtin = meta.get("gtin")

    menor_preco = estabelecimentos[0].preco if estabelecimentos else None
    maior_preco = max((e.preco for e in estabelecimentos), default=None)
    mediana_reg = (
        round(statistics.median([e.preco for e in estabelecimentos]), 2)
        if estabelecimentos
        else None
    )
    estab_mais_barato = estabelecimentos[0].nome_estabelecimento if estabelecimentos else None

    economia_reais = round((maior_preco - menor_preco), 2) if (menor_preco and maior_preco and maior_preco > menor_preco) else 0.0
    economia_pct = round((economia_reais / maior_preco) * 100.0, 1) if (maior_preco and maior_preco > 0) else 0.0

    variacao_rel = (economia_reais / menor_preco) if (menor_preco and menor_preco > 0) else 0.0
    status_melhor = estabelecimentos[0].status_atualidade if estabelecimentos else "DESATUALIZADO"

    confiabilidade = calcular_indicador_confiabilidade(
        quantidade_usuarios_distintos=total_usuarios,
        quantidade_registros_validos=total_registros,
        status_atualidade_melhor=status_melhor,
        tem_gtin_ou_exata=bool(gtin or produto_id.startswith("prod_") or produto_id.startswith("gtin_")),
        variacao_relativa=variacao_rel,
    )

    resposta = ComparacaoProdutoResponse(
        produto_id=produto_id,
        nome_produto=nome_produto,
        nome_normalizado=nome_norm,
        marca=marca,
        categoria=categoria,
        quantidade_embalagem=qtd_emb,
        unidade_medida=un_med,
        unidade_padrao=un_pad,
        gtin=gtin,
        nivel_correspondencia="EXATA",
        regiao_consultada=f"{regiao['nome_cidade']} - {regiao['uf']}",
        abrangencia=abr_efetiva,
        menor_preco=menor_preco,
        maior_preco=maior_preco,
        mediana_regional=mediana_reg,
        estabelecimento_mais_barato=estab_mais_barato,
        economia_maxima_reais=economia_reais,
        economia_maxima_percentual=economia_pct,
        total_usuarios_contribuintes=total_usuarios,
        total_registros_validos=total_registros,
        ultima_atualizacao_sistema=ultima_iso or datetime.datetime.now(datetime.timezone.utc).isoformat(),
        confiabilidade=confiabilidade,
        estabelecimentos=estabelecimentos,
        similares_equivalentes=[],
    )

    _salvar_cache(chave_cache, resposta)
    return resposta


def pesquisar_produtos_colaborativos(
    uid: str,
    termo: str = "",
    municipio: Optional[str] = None,
    uf: Optional[str] = None,
    abrangencia: Optional[str] = None,
    raio_km: Optional[int] = None,
    estabelecimento_filtro: Optional[str] = None,
    ordenar_por: str = "menor_preco",
    limite: int = 25,
) -> PesquisaColaborativaResponse:
    """
    Pesquisa produtos com preços colaborativos na região do usuário,
    agrupando por `produto_id` normalizado e ordenando pelo menor preço.
    """
    prefs = obter_preferencias_usuario(uid) if (not municipio or not uf) else {}
    regiao = identificar_regiao(
        municipio=municipio or prefs.get("municipio"),
        uf=uf or prefs.get("uf"),
        codigo_ibge=prefs.get("codigo_ibge") if not municipio else None,
    )
    abr_efetiva = abrangencia or prefs.get("abrangencia", "cidade_e_proximos")
    raio_efetivo = int(raio_km or prefs.get("raio_km", 30))
    limite_seguro = min(max(1, limite), 50)

    termo_limpo = remover_acentos(termo or "").strip().lower()
    chave_cache = f"pesq:{termo_limpo}:{regiao['uf']}:{regiao['cidade_id']}:{abr_efetiva}:{raio_efetivo}:{estabelecimento_filtro or ''}:{ordenar_por}:{limite_seguro}"
    em_cache = _obter_cache(chave_cache)
    if em_cache is not None:
        return em_cache

    cidades_elegiveis, distancias = obter_cidades_abrangencia(
        regiao_base=regiao,
        abrangencia=abr_efetiva,
        raio_km=raio_efetivo,
    )

    tokens = [t for t in termo_limpo.split() if len(t) >= 2]
    token_principal = tokens[0] if tokens else None

    registros = _buscar_registros_firestore_regiao(
        cidades_elegiveis=cidades_elegiveis,
        uf=regiao["uf"],
        token_busca=token_principal,
        limite=200,
    )

    # Se o usuário pesquisou uma frase com múltiplos termos (ex: "arroz 5kg"), filtra os tokens adicionais
    if len(tokens) > 1:
        filtrados_tokens = []
        for r in registros:
            tks_doc = set(r.get("tokens_busca") or [])
            nome_doc = remover_acentos(str(r.get("nome_produto_normalizado", ""))).lower()
            if all(tk in tks_doc or tk in nome_doc for tk in tokens):
                filtrados_tokens.append(r)
        registros = filtrados_tokens

    if estabelecimento_filtro:
        est_f = estabelecimento_filtro.strip().lower()
        registros = [
            r for r in registros
            if est_f in str(r.get("nome_estabelecimento", "")).lower()
            or est_f == str(r.get("estabelecimento_id", "")).lower()
        ]

    # Agrupa registros por produto_id
    por_produto: Dict[str, List[Dict[str, Any]]] = {}
    for r in registros:
        pid = r.get("produto_id")
        if pid:
            por_produto.setdefault(pid, []).append(r)

    resumos: List[ResumoProdutoPesquisaSchema] = []
    for pid, regs_prod in por_produto.items():
        estabs, qtd_usuarios, qtd_regs, _ = consolidar_precos_por_estabelecimento(
            registros=regs_prod,
            distancias_cidades=distancias,
        )
        if not estabs:
            continue

        meta = regs_prod[0]
        melhor = estabs[0]
        maior_p = max(e.preco for e in estabs)
        econ_reais = round(max(0.0, maior_p - melhor.preco), 2)
        econ_pct = round((econ_reais / maior_p) * 100.0, 1) if maior_p > 0 else 0.0

        qtd_emb = float(meta.get("quantidade", 1.0))
        un_med = str(meta.get("unidade_medida", "UN"))
        un_pad = str(meta.get("unidade_padrao", "UN"))
        marca = meta.get("marca_nome")

        qtd_fmt = int(qtd_emb) if qtd_emb == int(qtd_emb) else qtd_emb
        subtitulo = f"{marca + ' · ' if marca else ''}{qtd_fmt} {un_med}"

        conf = calcular_indicador_confiabilidade(
            quantidade_usuarios_distintos=qtd_usuarios,
            quantidade_registros_validos=qtd_regs,
            status_atualidade_melhor=melhor.status_atualidade,
            tem_gtin_ou_exata=True,
            variacao_relativa=(econ_reais / melhor.preco) if melhor.preco > 0 else 0.0,
        )

        resumos.append(
            ResumoProdutoPesquisaSchema(
                produto_id=pid,
                nome_produto=meta.get("nome_exibicao") or meta.get("nome_produto_normalizado") or pid,
                subtitulo=subtitulo,
                marca=marca,
                categoria=meta.get("categoria_id", "mercearia_geral"),
                quantidade_embalagem=qtd_emb,
                unidade_medida=un_med,
                gtin=meta.get("gtin"),
                nivel_correspondencia="EXATA",
                menor_preco=melhor.preco,
                maior_preco=maior_p,
                preco_por_unidade=melhor.preco_por_unidade,
                unidade_padrao=un_pad,
                estabelecimento_mais_barato=melhor.nome_estabelecimento,
                nome_cidade=melhor.nome_cidade,
                uf=melhor.uf,
                economia_potencial_reais=econ_reais,
                economia_potencial_percentual=econ_pct,
                total_estabelecimentos=len(estabs),
                total_usuarios_distintos=qtd_usuarios,
                total_registros_validos=qtd_regs,
                data_ultima_compra=melhor.data_compra,
                rotulo_tempo=melhor.rotulo_tempo,
                status_atualidade=melhor.status_atualidade,
                confiabilidade=conf,
                estabelecimentos_preview=estabs[:5],
            )
        )

    if ordenar_por == "maior_economia":
        resumos.sort(key=lambda x: (-x.economia_potencial_reais, x.menor_preco))
    else:
        resumos.sort(key=lambda x: (x.menor_preco, -x.total_estabelecimentos))

    resumos_paginados = resumos[:limite_seguro]
    resposta = PesquisaColaborativaResponse(
        termo_pesquisado=termo,
        cidade_referencia=regiao["nome_cidade"],
        uf_referencia=regiao["uf"],
        abrangencia=abr_efetiva,
        raio_km=raio_efetivo,
        total_encontrados=len(resumos_paginados),
        ultima_atualizacao_consulta=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        produtos=resumos_paginados,
    )

    _salvar_cache(chave_cache, resposta)
    return resposta


def consultar_historico_produto(
    uid: str,
    produto_id: str,
    periodo_dias: int = 90,
    municipio: Optional[str] = None,
    uf: Optional[str] = None,
    abrangencia: Optional[str] = None,
) -> HistoricoProdutoResponse:
    prefs = obter_preferencias_usuario(uid)
    regiao = identificar_regiao(
        municipio=municipio or prefs["municipio"],
        uf=uf or prefs["uf"],
    )
    abr_efetiva = abrangencia or prefs.get("abrangencia", "cidade_e_proximos")
    cidades_elegiveis, _ = obter_cidades_abrangencia(regiao, abr_efetiva, prefs.get("raio_km", 30))

    registros = _buscar_registros_firestore_regiao(
        cidades_elegiveis=cidades_elegiveis,
        uf=regiao["uf"],
        produto_id=produto_id,
        limite=200,
    )

    pontos, tendencia, variacao_pct = construir_historico_evolucao(
        registros=registros,
        periodo_dias=periodo_dias,
    )
    nome_prod = registros[0].get("nome_exibicao", produto_id) if registros else produto_id

    return HistoricoProdutoResponse(
        produto_id=produto_id,
        nome_produto=nome_prod,
        regiao_consultada=f"{regiao['nome_cidade']} - {regiao['uf']}",
        periodo_dias=periodo_dias,
        tendencia=tendencia,
        variacao_periodo_percentual=variacao_pct,
        pontos=pontos,
    )

