import base64
import datetime
import json
import logging
import os
import sys
from typing import Any, Dict

# Garante acesso aos módulos da raiz da API (firebase.py, etc.)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backup_firestore")


def _derivar_chave(senha: str, salt: bytes) -> bytes:
    """Deriva uma chave simétrica de 32 bytes usando PBKDF2HMAC (padrão NIST)."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))


def serializar_firestore(obj: Any) -> Any:
    """Serializa tipos nativos do Firestore (Datetime, GeoPoint, DocumentReference)."""
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    if hasattr(obj, "latitude") and hasattr(obj, "longitude"):
        return {"latitude": obj.latitude, "longitude": obj.longitude}
    if hasattr(obj, "path"):
        return {"_ref": obj.path}
    if isinstance(obj, dict):
        return {k: serializar_firestore(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [serializar_firestore(item) for item in obj]
    return obj


def exportar_firestore(output_dir: str, senha_criptografia: str = None) -> str:
    """
    Exporta documentos e subcoleções do Firestore para arquivo JSON criptografado ou estruturado.
    Salva em output_dir (fora do repositório Git).
    """
    from firebase import db

    timestamp_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    timestamp_slug = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    dados_backup: Dict[str, Any] = {
        "versao_formato": "1.0",
        "timestamp_utc": timestamp_iso,
        "total_usuarios": 0,
        "total_notas": 0,
        "usuarios": {},
        "colecoes_adicionais": {},
    }

    logger.info("Iniciando exportação do Firestore...")

    # 1. Exporta coleção /usuarios e subcoleção /notas
    usuarios_ref = db.collection("usuarios").stream()
    total_usuarios = 0
    total_notas = 0

    for u_doc in usuarios_ref:
        total_usuarios += 1
        uid = u_doc.id
        u_dados = serializar_firestore(u_doc.to_dict() or {})

        notas = {}
        notas_stream = db.collection("usuarios").document(uid).collection("notas").stream()
        for n_doc in notas_stream:
            total_notas += 1
            notas[n_doc.id] = serializar_firestore(n_doc.to_dict() or {})

        dados_backup["usuarios"][uid] = {
            "perfil": u_dados,
            "notas": notas,
        }

    dados_backup["total_usuarios"] = total_usuarios
    dados_backup["total_notas"] = total_notas

    # 2. Garante que o diretório de destino exista
    os.makedirs(output_dir, exist_ok=True)

    json_str = json.dumps(dados_backup, indent=2, ensure_ascii=False)

    if senha_criptografia:
        # Criptografia AES-128-CBC com autenticação HMAC (Fernet)
        salt = os.urandom(16)
        chave = _derivar_chave(senha_criptografia, salt)
        fernet = Fernet(chave)
        payload_cifrado = fernet.encrypt(json_str.encode("utf-8"))

        nome_arquivo = f"notaflow_backup_{timestamp_slug}.enc"
        caminho_final = os.path.join(output_dir, nome_arquivo)

        with open(caminho_final, "wb") as f:
            # Armazena o salt nos primeiros 16 bytes
            f.write(salt + payload_cifrado)

        logger.info(f"Backup CRIPTOGRAFADO salvo com sucesso em: {caminho_final}")
    else:
        nome_arquivo = f"notaflow_backup_{timestamp_slug}.json"
        caminho_final = os.path.join(output_dir, nome_arquivo)

        with open(caminho_final, "w", encoding="utf-8") as f:
            f.write(json_str)

        logger.info(f"Backup JSON salvo em: {caminho_final}")

    logger.info(f"Resumo da exportação: {total_usuarios} usuários, {total_notas} notas fiscais.")
    return caminho_final


if __name__ == "__main__":
    # Pasta padrão local fora do repositório
    default_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "notaflow-backups"))
    target_dir = os.getenv("BACKUP_OUTPUT_DIR", default_dir)
    backup_pass = os.getenv("BACKUP_ENCRYPTION_PASSWORD")

    print(f"Diretório de destino: {target_dir}")
    arquivo_gerado = exportar_firestore(target_dir, senha_criptografia=backup_pass)
    print(f"Concluído: {arquivo_gerado}")

