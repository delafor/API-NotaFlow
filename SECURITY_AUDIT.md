# Relatório de Auditoria de Segurança e Arquitetura — NotaFlow API

Data da Auditoria: 07 de Outubro de 2026  
Escopo: Backend FastAPI independente (`E:\Programacao\API-NotaFlow`)  

---

## 🎯 Resumo Executivo

Esta auditoria técnica analisou a arquitetura, endpoints, gestão de credenciais, fluxo de requisições HTTP externas, manipulação de dados e configurações da **NotaFlow API**.

A API possui funcionalidades operacionais de scraping e extração de dados fiscais (BP-e e NFC-e), contudo apresenta vulnerabilidades graves de **Controle de Acesso (Autenticação/Autorização)** e **Server-Side Request Forgery (SSRF)** que devem ser corrigidas obrigatoriamente antes de qualquer implantação em produção ou exposição pública.

---

## 📑 Vulnerabilidades Encontradas e Plano de Correção

### 1. Ausência Total de Autenticação e Autorização (IDOR & Broken Access Control)
- **Severidade**: **CRÍTICA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**: As rotas `/notas/{nota_id}`, `/notas/{nota_id}/extrair` e `/notas/importar` não exigem nenhum token de autenticação (como Firebase Auth ID Token). Além disso, as consultas ao Firestore utilizam a coleção global `db.collection("notas")` em vez de verificar o escopo por usuário (`usuarios/{uid}/notas/{nota_id}`).
- **Risco de Exploração**: Qualquer usuário na internet pode visualizar, extrair ou alterar notas fiscais de qualquer outro cliente conhecendo ou adivinhando o `nota_id` (Insecure Direct Object Reference - IDOR).
- **Recomendação**: Implementar um middleware ou dependência FastAPI de validação do token JWT do Firebase Auth (`firebase_admin.auth.verify_id_token`), garantindo que apenas usuários autenticados acessem suas próprias notas.
- **Plano de Correção**:
  1. Criar módulo `auth.py` com dependência `get_current_user_uid` usando `firebase_admin.auth`.
  2. Ajustar as rotas para exigir a dependência de autenticação.
  3. Atualizar o caminho de acesso ao Firestore para `usuarios/{uid}/notas/{nota_id}`.

---

### 2. Server-Side Request Forgery (SSRF) Direta e Indireta via Parsing HTML
- **Severidade**: **CRÍTICA**
- **Arquivo afetado**: [parser.py](file:///E:/Programacao/API-NotaFlow/parser.py), [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**:
  1. O endpoint `/notas/importar` aceita qualquer string em `data.url` e dispara requisições HTTP externas via `requests.get()` com `allow_redirects=True`.
  2. O `parser.py` inspeciona a tag `<form id="frmConsultaQrCode">` do HTML retornado e faz um `POST` automático para o endereço informado no atributo `action`. Se um atacante retornar uma página contendo um `action` apontando para um IP interno ou URL maliciosa, a API executará a requisição `POST` com os dados do formulário sem validação.
- **Risco de Exploração**: Um atacante pode enviar URLs apontando para IPs privados/locais (`127.0.0.1`, `10.x.x.x`, `192.168.x.x`), endpoints de metadados de provedores de nuvem (`http://169.254.169.254` na AWS/GCP), ou usar redirecionamentos HTTP / formulários HTML maliciosos para forçar o backend a realizar varreduras e requisições internas não autorizadas.
- **Recomendação**:
  1. Validar e sanitizar a URL de entrada usando um esquema restrito (`http`/`https`) e uma **Allowlist** de domínios fiscais confiáveis (ex: `*.svrs.rs.gov.br`, `*.sefaz.ba.gov.br`, etc.).
  2. Bloquear requisições a endereços IP privados, locais e de loopback (usando resolução DNS antes do request).
  3. Validar a URL de destino da tag `action` no formulário antes de executar o `session.post()`.
- **Plano de Correção**:
  1. Criar um utilitário de validação de URL (`security.py` ou `validator.py`).
  2. Aplicar verificação de domínio e resolução IP antes de `session.get()` e `session.post()`.
  3. Desativar redirecionamentos automáticos perigosos ou re-validar a URL no handler de redirecionamento.

---

### 3. Escrita Não Controlada de Arquivos em Disco (`bpe.html`)
- **Severidade**: **ALTA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**: No endpoint `/notas/importar`, o HTML baixado é salvo diretamente no disco (`with open("bpe.html", "w") as arquivo`).
- **Risco de Exploração**:
  - **Condição de Corrida (Race Condition)**: Múltiplas requisições simultâneas tentarão escrever no mesmo arquivo, corrompendo os dados ou gerando erros de concorrência.
  - **Vazamento de PII**: Dados pessoais e fiscais contidos nas notas ficam persistidos em texto simples no disco do servidor.
  - **Esgotamento de Armazenamento**: Possibilidade de degradação I/O.
- **Recomendação**: Remover a gravação física de `bpe.html` em disco. Manter o processamento exclusivamente em memória.
- **Plano de Correção**:
  1. Remover o bloco `with open("bpe.html", ...)` do `main.py`.
  2. Se logs de debug forem necessários em desenvolvimento, utilizar um parâmetro configurável no `.env` (`SAVE_DEBUG_HTML=false`).

---

### 4. Vazamento de Exceções e Detalhes Internos (Information Disclosure)
- **Severidade**: **ALTA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**: Os blocos `except Exception as e:` nos endpoints capturam qualquer exceção e retornam `HTTPException(status_code=400, detail=str(e))` além de invocar `traceback.print_exc()`.
- **Risco de Exploração**: Exposição de detalhes internos da aplicação, estrutura de arquivos, erros de conexão com banco de dados e bibliotecas internas, auxiliando um atacante na fase de reconhecimento.
- **Recomendação**: Retornar mensagens de erro genéricas e tratadas para o cliente (ex: `"Erro ao processar a nota fiscal"`) e registrar o erro detalhado apenas nos logs internos do servidor.
- **Plano de Correção**:
  1. Criar um handler global de exceções ou padronizar as respostas de erro nas rotas.
  2. Garantir que `detail` contenha apenas mensagens amigáveis e não confidenciais.

---

### 5. Configuração Permissiva de CORS (`allow_origins=["*"]`)
- **Severidade**: **ALTA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**: O middleware `CORSMiddleware` está configurado com `allow_origins=["*"]`.
- **Risco de Exploração**: Permite que qualquer site na web faça chamadas cross-origin para a API a partir do navegador de um usuário.
- **Recomendação**: Restringir as origens permitidas via variável de ambiente `ALLOWED_ORIGINS` (ex: domínios do app web/mobile ou desativar CORS se for consumido apenas por aplicativos nativos).
- **Plano de Correção**:
  1. Adicionar `ALLOWED_ORIGINS` ao `.env.example`.
  2. Ler a lista de origens em `main.py` e passar para `CORSMiddleware`.

---

### 6. Ausência de Rate Limiting e Gestão de Esgotamento de Recursos
- **Severidade**: **MÉDIA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py), [parser.py](file:///E:/Programacao/API-NotaFlow/parser.py)
- **Motivo**: A API não possui limitação de taxa de requisições por IP ou usuário. Além disso, o timeout HTTP no `requests` é de 30 segundos e não há limite de tamanho de download (`Content-Length`).
- **Risco de Exploração**: Ataques de Negação de Serviço (DoS) e esgotamento da *threadpool* do servidor Uvicorn ao enviar múltiplas requisições lentas ou volumosas.
- **Recomendação**:
  1. Adicionar biblioteca de Rate Limiting (ex: `slowapi`).
  2. Reduzir o timeout HTTP para valores mais adequados (ex: 10s-15s).
  3. Adicionar verificação do tamanho da resposta no stream de download.
- **Plano de Correção**:
  1. Integrar `slowapi` no FastAPI.
  2. Ajustar os parâmetros `timeout` no `parser.py`.

---

### 7. Validação de Entrada Insuficiente nos Schemas Pydantic
- **Severidade**: **MÉDIA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py)
- **Motivo**: O modelo `NotaRequest` define `url: str` sem validação de formato `HttpUrl` ou limites de caracteres.
- **Risco de Exploração**: Envio de payloads mal formatados ou esquemas arbitrários (`file://`, `data:`, `gopher://`).
- **Recomendação**: Utilizar `HttpUrl` do Pydantic ou validações personalizadas de formato de URL.
- **Plano de Correção**:
  1. Atualizar o modelo `NotaRequest` com `HttpUrl` ou validações específicas.

---

### 8. Gestão de Logs e Dados Pessoais (PII)
- **Severidade**: **BAIXA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py), [extractor.py](file:///E:/Programacao/API-NotaFlow/extractor.py)
- **Motivo**: Utilização de `print("NOTA:", nota)` no console, expondo dados pessoais (PII) como nomes, trechos de documentos e valores nos logs stdout de produção.
- **Recomendação**: Substituir chamadas diretas de `print` pelo módulo padrão `logging` do Python, com níveis apropriados (`INFO`, `WARNING`, `ERROR`) e sanitização de dados.
- **Plano de Correção**:
  1. Configurar o sistema de `logging`.
  2. Remover `print` com dados completos das notas.

---

### 9. Código Legado, Duplicado e Débito Técnico
- **Severidade**: **BAIXA**
- **Arquivo afetado**: [main.py](file:///E:/Programacao/API-NotaFlow/main.py), [extractor.py](file:///E:/Programacao/API-NotaFlow/extractor.py), [scraper.py](file:///E:/Programacao/API-NotaFlow/scraper.py)
- **Motivo**:
  - `main.py` contém 160 linhas de código legado comentado no início do arquivo.
  - `extractor.py` contém uma re-definição interna da função `extrair_nota` e linhas duplicadas.
  - `scraper.py` é um arquivo não utilizado no fluxo principal.
- **Recomendação**: Limpar código comentado e duplicado para melhorar a legibilidade e manutenibilidade.
- **Plano de Correção**:
  1. Remover blocos comentados não utilizados de `main.py`.
  2. Corrigir a estrutura interna de `extractor.py`.

---

### 10. Cobertura de Testes Insuficiente
- **Severidade**: **BAIXA**
- **Arquivo afetado**: [tests/](file:///E:/Programacao/API-NotaFlow/tests)
- **Motivo**: Apenas existe o teste estático `test_parser.py`. Não há testes de rotas da API, testes de autenticação, testes de validação de URL ou testes de erro.
- **Recomendação**: Criar testes automatizados com `pytest` e `TestClient` do FastAPI.
- **Plano de Correção**:
  1. Adicionar `pytest` e `httpx` ao `requirements.txt`.
  2. Criar `test_main.py` cobrindo endpoints e validações de segurança.

---

## 🔒 Auditoria Especifica de Credenciais e Arquivos Sensíveis

- **Status de Credenciais**:
  - O projeto possui os arquivos `firebase-service-account.json` e `formulario-d5aa9-firebase-adminsdk-fbsvc-b842baef77.json`.
  - Ambos os arquivos foram corretamente adicionados ao [.gitignore](file:///E:/Programacao/API-NotaFlow/.gitignore) e **não** estão expostos em nenhum código-fonte nem em arquivos de documentação.
  - A conexão ao Firebase foi abstraída via variável de ambiente `FIREBASE_CREDENTIALS_PATH` em [firebase.py](file:///E:/Programacao/API-NotaFlow/firebase.py).

---

## 📊 Matriz de Risco

| Vulnerabilidade | Severidade | Arquivo Principal | Risco de Exploração |
|---|---|---|---|
| Ausência de Autenticação / Autoriação (IDOR) | **Crítica** | `main.py` | Acesso e alteração não autorizada de dados |
| Vulnerabilidade de SSRF (Direta e Form Actions) | **Crítica** | `parser.py` / `main.py` | Acesso à rede interna / cloud metadata |
| Escrita de Arquivos no Disco (`bpe.html`) | **Alta** | `main.py` | Concorrência, vazamento de PII |
| Exposição de Detalhes de Erros (Stack Traces) | **Alta** | `main.py` | Reconhecimento e vazamento de informações |
| CORS Permissivo (`*`) | **Alta** | `main.py` | Requisições cross-origin não autorizadas |
| Ausência de Rate Limiting e Timeout Longo | **Média** | `main.py` / `parser.py` | Negação de serviço (DoS) |
| Validação de Entrada Fraca no Pydantic | **Média** | `main.py` | Envio de URLs e esquemas maliciosos |
| Logs com Dados Pessoais (PII) | **Baixa** | `extractor.py` | Vazamento em logs stdout |
| Código Duplicado e Legado | **Baixa** | `main.py` / `extractor.py` | Débito técnico |
| Falta de Testes de Endpoints | **Baixa** | `tests/` | Regressões de segurança |


