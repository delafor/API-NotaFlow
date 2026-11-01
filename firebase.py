import os

import firebase_admin
from firebase_admin import credentials, firestore

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# Modo 1: Caminho para arquivo de credenciais (Local ou Docker)
cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-service-account.json")

if os.path.exists(cred_path):
    cred = credentials.Certificate(cred_path)
elif os.getenv("FIREBASE_PRIVATE_KEY") and os.getenv("FIREBASE_PROJECT_ID"):
    # Modo 2: Variáveis de ambiente diretas (PaaS/Produção Cloud)
    private_key = os.getenv("FIREBASE_PRIVATE_KEY", "").replace("\\n", "\n")
    cred = credentials.Certificate({
        "type": "service_account",
        "project_id": os.getenv("FIREBASE_PROJECT_ID"),
        "private_key": private_key,
        "client_email": os.getenv("FIREBASE_CLIENT_EMAIL"),
        "token_uri": "https://oauth2.googleapis.com/token",
    })
else:
    # Fallback seguro para inicialização em ambiente de teste ou credenciais padrão do GCP
    try:
        cred = credentials.Certificate(cred_path)
    except Exception:
        cred = credentials.ApplicationDefault()

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()