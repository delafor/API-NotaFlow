import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import firebase_admin.auth as firebase_auth
from firebase import db  # Ensures firebase_admin is initialized

logger = logging.getLogger(__name__)

security_scheme = HTTPBearer(auto_error=False)


def get_current_user_uid(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> str:
    """
    FastAPI dependency that validates Firebase ID Token passed in Authorization header.
    Returns the authenticated user's UID.
    Raises HTTP 401 Unauthorized if missing, invalid, or expired.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação não fornecido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials

    try:
        decoded_token = firebase_auth.verify_id_token(token)
        uid = decoded_token.get("uid")

        if not uid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token de autenticação não contém um UID válido",
                headers={"WWW-Authenticate": "Bearer"},
            )

        return uid

    except firebase_auth.ExpiredIdTokenError:
        logger.warning("Tentativa de acesso com Firebase ID Token expirado")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except firebase_auth.InvalidIdTokenError as e:
        logger.warning(f"Tentativa de acesso com Firebase ID Token inválido: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except Exception as e:
        logger.error(f"Erro ao verificar token no Firebase Auth: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falha na autenticação do usuário",
            headers={"WWW-Authenticate": "Bearer"},
        )

