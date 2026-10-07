# NotaFlow API

API em Python com FastAPI responsável pelo parsing, extração e sincronização de dados de comprovantes fiscais (BP-e e NFC-e) do sistema NotaFlow.

---

## 📌 Objetivo

A **NotaFlow API** fornece serviços para obtenção e parsing de dados de bilhetes e notas fiscais eletrônicas a partir de URLs e QR Codes, persistindo os dados extraídos no Firebase Firestore.

---

## 🏗️ Arquitetura Resumida

- **Framework**: [FastAPI](https://fastapi.tiangolo.com/) (ASGI server com Uvicorn)
- **Scraper / Parser**: [Requests](https://requests.readthedocs.io/) & [BeautifulSoup4](https://www.crummy.com/software/BeautifulSoup/)
- **Banco de Dados**: [Firebase Firestore](https://firebase.google.com/docs/firestore) via `firebase-admin`
- **Validação de Schemas**: [Pydantic](https://docs.pydantic.dev/)

### Estrutura de Arquivos

```text
notaflow-api/
├── main.py              # Ponto de entrada FastAPI e rotas da aplicação
├── parser.py            # Requisições HTTP e manipulação de formulários de consulta
├── extractor.py         # Parsing de HTML para BP-e e NFC-e
├── firebase.py          # Conexão e inicialização do Firebase Admin SDK
├── requirements.txt     # Dependências Python do projeto
├── .env.example         # Exemplo de variáveis de ambiente
├── .gitignore           # Regras do Git para arquivos ignorados
├── README.md            # Documentação do projeto
├── SECURITY.md          # Diretrizes e políticas de segurança
└── tests/
    └── test_parser.py   # Testes automatizados do parser
```

---

## 🚀 Como Executar Localmente

### 1. Criar o Ambiente Virtual

No terminal (PowerShell ou Bash):

```bash
python -m venv venv
```

Ativar o ambiente virtual:

- **Windows (PowerShell)**:
  ```powershell
  .\venv\Scripts\Activate.ps1
  ```
- **Linux/macOS**:
  ```bash
  source venv/bin/activate
  ```

### 2. Instalar as Dependências

```bash
pip install -r requirements.txt
```

### 3. Configurar Variáveis de Ambiente e Credenciais

1. Copie o arquivo de exemplo `.env.example` para `.env`:
   ```bash
   cp .env.example .env
   ```
2. Insira o caminho do arquivo de credenciais do Firebase no `.env`:
   ```env
   FIREBASE_CREDENTIALS_PATH=firebase-service-account.json
   ```
3. Garanta que o arquivo `firebase-service-account.json` esteja na raiz do projeto (este arquivo **nunca** deve ser commitado no Git).

### 4. Executar em Modo de Desenvolvimento

```bash
uvicorn main:app --reload
```

A API estará acessível em `http://127.0.0.1:8000`.

A documentação interativa (Swagger UI) estará disponível em `http://127.0.0.1:8000/docs`.

---

## 🏭 Comando para Execução em Produção

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## 📍 Endpoints Existentes

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/` | Healthcheck da API |
| `GET` | `/notas/{nota_id}` | Obtém dados de uma nota salva no Firestore |
| `POST` | `/notas/{nota_id}/extrair` | Baixa o HTML da URL salva na nota e atualiza dados extraídos |
| `POST` | `/notas/importar` | Recebe uma URL no body (`{"url": "..."}`) e retorna a nota extraída |

---

## 🔒 Observações de Segurança

- **Chaves de Serviço**: O arquivo `firebase-service-account.json` contém privilégios de administrador do Firebase. **Nunca compartilhe ou comite este arquivo**.
- **Variáveis de Ambiente**: Mantenha segredos e configurações locais no arquivo `.env`, o qual está incluído no `.gitignore`.
- **CORS**: Em produção, altere a permissão global do CORS no `main.py` para domínios específicos confiáveis.

