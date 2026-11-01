import base64
import json
import logging
import os
import sys
from typing import Any, Dict

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("restore_firestore")


def _derivar_chave(senha: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=100_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(senha.encode("utf-8")))


def carregar_dados_backup(caminho_arquivo: str, senha_criptografia: str = None) -> Dict[str, Any]:
    """Lê e descriptografa (se necessário) o arquivo de backup."""
    if not os.path.exists(caminho_arquivo):
        raise FileNotFoundError(f"Arquivo de backup não encontrado: {caminho_arquivo}")

    if caminho_arquivo.endswith(".enc"):
        if not senha_criptografia:
            raise ValueError("O arquivo está criptografado (.enc). Forneça a senha para descriptografar.")

        with open(caminho_arquivo, "rb") as f:
            conteudo = f.read()

        salt = conteudo[:16]
        payload = conteudo[16:]
        chave = _derivar_chave(senha_criptografia, salt)
        fernet = Fernet(chave)
        dados_json = fernet.decrypt(payload).decode("utf-8")
        return json.loads(dados_json)
    else:
        with open(caminho_arquivo, "r", encoding="utf-8") as f:
            return json.load(f)


def restaurar_firestore(caminho_arquivo: str, senha_criptografia: str = None, simular: bool = False) -> Dict[str, int]:
    """
    Restaura coleções e subcoleções no Firestore a partir de um arquivo de backup.
    Retorna a contagem de documentos restaurados.
    """
    from firebase import db

    dados_backup = carregar_dados_backup(caminho_arquivo, senha_criptografia)
    usuarios = dados_backup.get("usuarios", {})

    logger.info(f"Backup carregado. Timestamp original: {dados_backup.get('timestamp_utc')}")
    logger.info(f"Iniciando restauração... Simulação: {simular}")

    usuarios_restaurados = 0
    notas_restauradas = 0

    batch = db.batch()
    operacoes_no_batch = 0
    LIMITE_BATCH = 400  # Limite de segurança do Firestore é 500

    for uid, u_info in usuarios.items():
        u_perfil = u_info.get("perfil", {})
        u_ref = db.collection("usuarios").document(uid)

        if not simular:
            batch.set(u_ref, u_perfil, merge=True)
            operacoes_no_batch += 1

        usuarios_restaurados += 1

        notas = u_info.get("notas", {})
        for nota_id, nota_dados in notas.items():
            nota_ref = u_ref.collection("notas").document(nota_id)
            if not simular:
                batch.set(nota_ref, nota_dados, merge=True)
                operacoes_no_batch += 1

            notas_restauradas += 1

            if operacoes_no_batch >= LIMITE_BATCH and not simular:
                batch.commit()
                batch = db.batch()
                operacoes_no_batch = 0

    if operacoes_no_batch > 0 and not simular:
        batch.commit()

    logger.info(f"Restauração finalizada: {usuarios_restaurados} usuários, {notas_restauradas} notas.")
    return {
        "usuarios_restaurados": usuarios_restaurados,
        "notas_restauradas": notas_restauradas,
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python restore_firestore.py <caminho_arquivo_backup> [senha]")
        sys.exit(1)

    arquivo = sys.argv[1]
    senha = sys.argv[2] if len(sys.argv) > 2 else os.getenv("BACKUP_ENCRYPTION_PASSWORD")
    restaurar_firestore(arquivo, senha)

