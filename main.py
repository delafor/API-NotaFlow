import logging
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from auth import get_current_user_uid
from firebase import db
from extractor import extrair_nota
from parser import buscar_pagina
from schemas import NotaFiscalSchema, gerar_id_deterministico_nota
from security import rate_limiter, validate_url

# ------------------------------------------------------------
# LOGGING SETUP
# ------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("notaflow_api")

app = FastAPI(
    title="NotaFlow API",
    description="API para obtenção, parsing e extração de comprovantes fiscais (BP-e e NFC-e).",
    version="1.0.0",
)

# ------------------------------------------------------------
# CORS CONFIGURATION
# ------------------------------------------------------------
allowed_origins_raw = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = (
    [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
    if allowed_origins_raw != "*"
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ------------------------------------------------------------
# PYDANTIC SCHEMAS DE ENTRADA
# ------------------------------------------------------------
class NotaRequest(BaseModel):
    url: str = Field(
        ...,
        description="URL da Nota Fiscal (BP-e / NFC-e) obtida via QR Code ou consulta.",
        max_length=2048,
    )

    @field_validator("url")
    @classmethod
    def validate_url_field(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("A URL não pode estar vazia.")
        v_clean = v.strip()
        # Perform security validation check
        validate_url(v_clean)
        return v_clean


# ------------------------------------------------------------
# GLOBAL EXCEPTION HANDLERS (SANITIZED ERRORS)
# ------------------------------------------------------------
@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    logger.warning(f"Erro de validação na requisição [{request.url.path}]: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"detail": str(exc)},
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    logger.error(f"Erro interno não tratado [{request.url.path}]: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Erro interno ao processar a requisição."},
    )


# ------------------------------------------------------------
# HELPER FUNCTIONS
# ------------------------------------------------------------
def _obter_documento_nota(uid: str, nota_id: str):
    """
    Recupera com segurança o documento da nota no escopo do usuário autenticado:
    usuarios/{uid}/notas/{nota_id}
    Garante que o UID nunca seja alterado ou acessado por terceiros.
    """
    doc_ref = (
        db.collection("usuarios")
        .document(uid)
        .collection("notas")
        .document(nota_id)
    )

    doc = doc_ref.get()
    if not doc.exists:
        return None, None

    return doc_ref, doc.to_dict()


# ------------------------------------------------------------
# ENDPOINTS
# ------------------------------------------------------------

@app.get("/")
def home():
    """Health check endpoint público."""
    return {"mensagem": "NotaFlow API funcionando!"}


@app.get("/notas/{nota_id}")
def buscar_nota(
    nota_id: str,
    uid: str = Depends(get_current_user_uid),
):
    """
    Busca uma nota fiscal específica do usuário autenticado no Firestore.
    """
    doc_ref, dados = _obter_documento_nota(uid, nota_id)

    if not dados:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )

    return {
        "id": nota_id,
        "linkNota": dados.get("linkNota"),
        "dados": dados,
    }


@app.post("/notas/{nota_id}/extrair")
def extrair_dados_nota(
    nota_id: str,
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    """
    Executa a extração dos dados fiscais de uma nota já salva na conta do usuário autenticado.
    Utiliza transação nativa do Firestore para garantir atomicidade, idempotência e integridade.
    """
    # Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"{uid}:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições excedido. Aguarde um instante.",
        )

    doc_ref, dados = _obter_documento_nota(uid, nota_id)

    if not doc_ref or not dados:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nota não encontrada",
        )

    # Idempotência: Se já foi extraída com sucesso E contém produtos com valor_unitario, retorna os dados existentes
    prods = dados.get("dadosExtraidos", {}).get("produtos", [])
    tem_prods_sem_unitario = any(p.get("valor_unitario") is None for p in prods) if prods else False

    if dados.get("status") == "extraida" and dados.get("dadosExtraidos") and not tem_prods_sem_unitario:
        logger.info(f"Nota {nota_id} já extraída previamente com sucesso. Retornando dados em cache.")
        return {
            "sucesso": True,
            "id": nota_id,
            "url": dados.get("linkNota"),
            "nota": dados.get("dadosExtraidos"),
            "idempotente": True,
        }

    url = dados.get("linkNota")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A nota não possui linkNota cadastrado",
        )

    logger.info(f"Extraindo nota id={nota_id} para uid={uid}")

    try:
        html = buscar_pagina(url)
        dados_brutos = extrair_nota(html)

        # Validação estrita com Pydantic antes de qualquer persistência
        # Impede salvar dados incompletos ou corrompidos
        nota_validada = NotaFiscalSchema(**dados_brutos).model_dump()

        # Transação nativa do Firestore para atualização atômica e consistente
        transaction = db.transaction()

        from google.cloud.firestore import Transaction

        @db.transaction()
        def _atualizar_transacao(trans: Transaction):
            snapshot = doc_ref.get(transaction=trans)
            if not snapshot.exists:
                raise HTTPException(status_code=404, detail="Nota não encontrada.")

            trans.update(doc_ref, {
                "dadosExtraidos": nota_validada,
                "status": "extraida",
                "tipo": nota_validada.get("tipo"),
                "total": nota_validada.get("total"),
                "chave": nota_validada.get("chave"),
                "owner_uid": uid,  # Garante que o UID de propriedade seja preservado
            })

        _atualizar_transacao(transaction)

        return {
            "sucesso": True,
            "id": nota_id,
            "url": url,
            "nota": nota_validada,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao extrair nota {nota_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao extrair dados da nota fiscal.",
        )


@app.post("/notas/importar")
def importar_nota(
    data: NotaRequest,
    request: Request,
    uid: str = Depends(get_current_user_uid),
):
    """
    Importa e extrai em tempo real os dados de uma nota fiscal a partir de sua URL/QR Code.
    Utiliza identificadores determinísticos para evitar notas duplicadas e transação nativa do Firestore.
    """
    # Rate Limiting
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"{uid}:{client_ip}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Limite de requisições excedido. Aguarde um instante.",
        )

    url = data.url
    logger.info(f"Importando nota via URL para uid={uid}")

    try:
        html = buscar_pagina(url)
        dados_brutos = extrair_nota(html)

        # Validação estrita de campos, totais e produtos com Pydantic
        # Se a extração falhar ou tiver campos obrigatórios ausentes, gera exceção e NÃO salva
        nota_validada = NotaFiscalSchema(**dados_brutos).model_dump()

        # Identificador determinístico da nota fiscal (chave fiscal / hash determinístico)
        nota_id = gerar_id_deterministico_nota(nota_validada, url_origem=url)

        doc_ref = (
            db.collection("usuarios")
            .document(uid)
            .collection("notas")
            .document(nota_id)
        )

        from google.cloud.firestore import Transaction

        transaction = db.transaction()

        @db.transaction()
        def _salvar_transacao(trans: Transaction):
            snapshot = doc_ref.get(transaction=trans)
            if snapshot.exists:
                snap_dados = snapshot.to_dict() or {}
                prods_existentes = snap_dados.get("dadosExtraidos", {}).get("produtos", [])
                tem_sem_unitario = any(p.get("valor_unitario") is None for p in prods_existentes) if prods_existentes else False
                if not tem_sem_unitario:
                    logger.info(f"Nota já existe para o usuário {uid} com ID {nota_id}. Operação idempotente.")
                    return snap_dados, True

            dados_salvar = {
                "id": nota_id,
                "owner_uid": uid,
                "linkNota": url,
                "status": "extraida",
                "dadosExtraidos": nota_validada,
                "tipo": nota_validada.get("tipo"),
                "total": nota_validada.get("total"),
                "chave": nota_validada.get("chave"),
            }
            trans.set(doc_ref, dados_salvar)
            return dados_salvar, False

        doc_dados, ja_existia = _salvar_transacao(transaction)

        return {
            "sucesso": True,
            "id": nota_id,
            "url": url,
            "nota": nota_validada,
            "idempotente": ja_existia,
        }

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao importar nota via URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao importar e processar a nota fiscal.",
        )