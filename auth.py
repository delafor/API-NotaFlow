import logging
import os
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


def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
) -> dict:
    """
    Dependência que valida se o usuário possui permissão de Administrador (RBAC).
    Verifica Firebase Custom Claims ('admin': True) ou lista explícita de UIDs/emails autorizados.
    Lança HTTP 403 Forbidden caso seja usuário comum sem privilégios.
    """
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação administrativo não fornecido",
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
            )

        # 1. Custom Claim do Firebase Auth: {"admin": True}
        is_admin_claim = decoded_token.get("admin") is True or decoded_token.get("role") == "admin"

        # 2. Verificação de lista autorizada via variável de ambiente (Fallback seguro)
        raw_uids = os.getenv("ADMIN_UIDS", "")
        admin_uids = [u.strip() for u in raw_uids.split(",") if u.strip()]

        raw_emails = os.getenv("ADMIN_EMAILS", "")
        admin_emails = [e.strip().lower() for e in raw_emails.split(",") if e.strip()]
        user_email = (decoded_token.get("email") or "").lower()

        is_authorized_admin = (
            is_admin_claim
            or (uid in admin_uids)
            or (bool(user_email) and user_email in admin_emails)
        )

        if not is_authorized_admin:
            logger.warning(f"Acesso negado: Usuário UID {uid} ({user_email}) tentou acessar rota administrativa sem permissão.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Acesso negado: Privilégios de administrador necessários.",
            )

        return decoded_token

    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação expirado",
        )
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token de autenticação inválido",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao verificar privilégios de administrador: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Falha ao verificar autorização administrativa",
        )

