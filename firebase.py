import os
import firebase_admin
from firebase_admin import credentials, firestore
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "firebase-service-account.json")
cred = credentials.Certificate(cred_path)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()