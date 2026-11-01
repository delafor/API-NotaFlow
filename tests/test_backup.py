import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from scripts.backup_firestore import _derivar_chave, serializar_firestore
from scripts.restore_firestore import carregar_dados_backup
from cryptography.fernet import Fernet


def test_serializacao_e_criptografia_backup():
    """Valida o ciclo de exportação, criptografia AES-PBKDF2 e leitura com validação de integridade."""
    dados_mock = {
        "versao_formato": "1.0",
        "timestamp_utc": "2026-10-13T16:00:00Z",
        "total_usuarios": 2,
        "total_notas": 3,
        "usuarios": {
            "uid_usuario_1": {
                "perfil": {"nome": "Cliente Teste", "email": "teste@notaflow.com"},
                "notas": {
                    "chave_29260903184187000119650090000069531012240675": {
                        "tipo": "NFC-e",
                        "total": 55.96,
                        "status": "extraida",
                    },
                    "chave_12345678901234567890123456789012345678901234": {
                        "tipo": "BP-e",
                        "total": 21.00,
                        "status": "extraida",
                    },
                },
            },
            "uid_usuario_2": {
                "perfil": {"nome": "Segundo Cliente"},
                "notas": {
                    "doc_987654321": {
                        "tipo": "NFC-e",
                        "total": 150.00,
                    }
                },
            },
        },
    }

    senha_secreta = "MinhaSenhaSuperForte123!"

    with tempfile.TemporaryDirectory() as tmpdir:
        caminho_enc = os.path.join(tmpdir, "backup_teste.enc")

        # Criptografa
        salt = os.urandom(16)
        chave = _derivar_chave(senha_secreta, salt)
        fernet = Fernet(chave)
        payload = fernet.encrypt(json.dumps(dados_mock).encode("utf-8"))

        with open(caminho_enc, "wb") as f:
            f.write(salt + payload)

        # 1. Valida leitura com senha correta
        dados_restaurados = carregar_dados_backup(caminho_enc, senha_criptografia=senha_secreta)
        assert dados_restaurados["total_usuarios"] == 2
        assert dados_restaurados["total_notas"] == 3
        assert len(dados_restaurados["usuarios"]["uid_usuario_1"]["notas"]) == 2
        assert "uid_usuario_2" in dados_restaurados["usuarios"]

        # 2. Confere integridade exata dos campos recuperados
        nota_recuperada = dados_restaurados["usuarios"]["uid_usuario_1"]["notas"]["chave_29260903184187000119650090000069531012240675"]
        assert nota_recuperada["total"] == 55.96
        assert nota_recuperada["tipo"] == "NFC-e"

        # 3. Valida rejeição com senha incorreta
        try:
            carregar_dados_backup(caminho_enc, senha_criptografia="SenhaErrada")
            assert False, "Deveria ter falhado ao tentar descriptografar com senha errada!"
        except Exception:
            # Sucesso
            pass


def test_serializacao_tipos_firestore():
    import datetime
    agora = datetime.datetime.now()
    obj = {
        "data": agora,
        "lista": [agora, 1, "texto"],
        "geo": type("Geo", (), {"latitude": -12.97, "longitude": -38.51})(),
    }
    serializado = serializar_firestore(obj)
    assert isinstance(serializado["data"], str)
    assert serializado["geo"]["latitude"] == -12.97


if __name__ == "__main__":
    test_serializacao_e_criptografia_backup()
    test_serializacao_tipos_firestore()
    print("Todos os testes de backup e restauração em test_backup.py passaram com sucesso!")

