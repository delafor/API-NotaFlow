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
# PYDANTIC SCHEMAS
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

    url = dados.get("linkNota")
    if not url:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A nota não possui linkNota cadastrado",
        )

    logger.info(f"Extraindo nota id={nota_id} para uid={uid}")

    try:
        html = buscar_pagina(url)
        nota = extrair_nota(html)

        doc_ref.update({
            "dadosExtraidos": nota,
            "status": "extraida",
        })

        return {
            "sucesso": True,
            "id": nota_id,
            "url": url,
            "nota": nota,
        }
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
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
    Exige autenticação Firebase Auth.
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

        # Opcional: salvar HTML para debug apenas se explicitamente habilitado no .env
        save_debug = os.getenv("SAVE_DEBUG_HTML", "false").lower() == "true"
        if save_debug:
            try:
                with open("bpe.html", "w", encoding="utf-8") as f:
                    f.write(html)
            except Exception as fe:
                logger.warning(f"Não foi possível salvar bpe.html para debug: {str(fe)}")

        nota = extrair_nota(html)

        return {
            "sucesso": True,
            "url": url,
            "nota": nota,
        }

    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(ve))
    except Exception as e:
        logger.error(f"Erro ao importar nota via URL: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Falha ao importar e processar a nota fiscal.",
        )