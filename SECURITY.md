# Política de Segurança — NotaFlow API

## 🛡️ Medidas de Segurança Implementadas

### 1. Autenticação e Autorização (Firebase Auth + Firestore Tenant Isolation)
- **Token Firebase Auth**: Todos os endpoints de notas (`/notas/{nota_id}`, `/notas/{nota_id}/extrair`, `/notas/importar`) exigem o cabeçalho `Authorization: Bearer <Firebase ID Token>`.
- **Validação com Firebase Admin SDK**: Os tokens ID são verificados usando `firebase_admin.auth.verify_id_token()`. Tokens ausentes, expirados ou manipulados são rejeitados com HTTP 401.
- **Isolamento de Dados por Usuário (Anti-IDOR)**: As operações no Firestore são estritamente restritas à subcoleção do UID autenticado (`usuarios/{uid}/notas/{nota_id}`). Tentativas de acessar notas de terceiros são negadas com HTTP 404 sem revelar a existência dos documentos.

### 2. Proteção contra SSRF (Server-Side Request Forgery)
- **Validação de Esquemas e Esquemas Proibidos**: Apenas conexões `http://` e `https://` são aceitas. Esquemas perigosos (`file://`, `ftp://`, `gopher://`, `data:`) e URLs contendo credenciais (`user:pass@host`) são terminantemente bloqueados.
- **Lista de Domínios Permitidos (Allowlist)**: A API aceita requisições apenas para domínios de órgãos fiscais reconhecidos (ex: `*.svrs.rs.gov.br`, `*.sefaz.ba.gov.br`, etc., configurados em `ALLOWED_DOMAINS`).
- **Filtro de Endereços IP (Anti-Internal / Cloud Metadata SSRF)**: Resolução de DNS realizada antes das requisições. IPs privados (`10.x`, `172.16.x`, `192.168.x`), loopback (`127.0.0.1`, `::1`), link-local (`169.254.x.x`), multicast, IPv4-mapped IPv6 e endpoints de metadados de nuvem (`169.254.169.254`, `metadata.google.internal`) são interceptados e bloqueados.
- **Redirecionamentos Seguros (Redirect Validation)**: `allow_redirects=False` é forçado em todas as chamadas HTTP. Cada redirecionamento (header `Location`) e cada formulário intermediário descobrindo URLs dinamicamente (tag `action`) passa novamente pela validação completa de SSRF antes de executar a nova requisição.

### 3. Controle de Esgotamento de Recursos e Rate Limiting
- **Limites de Payload e Streaming**: As respostas HTTP externas são lidas via streaming (`stream=True`) em chunks. Se a resposta ultrapassar `MAX_CONTENT_LENGTH` (padrão 5 MB), a conexão é abortada imediatamente.
- **Timeouts Rígidos**: Requisições utilizam timeouts separados de conexão (5s) e leitura (15s).
- **Proteção contra Abuso (Rate Limiter)**: Janela deslizante em memória limita requisições por IP e UID em rotas sensíveis de parsing (padrão 20 requisições/minuto), retornando HTTP 429 quando excedido.

### 4. Sanitização de Logs e Respostas de Erro
- **Sem Exposição de Stack Traces**: Erros internos são capturados globalmente. O cliente HTTP recebe mensagens genéricas sanitizadas sem vazamento de detalhes de infraestrutura ou banco de dados.
- **Logs Estruturados**: Utilização do módulo padrão `logging` em formato estruturado sem impressão em texto limpo de PII (dados pessoais/fiscais).

### 5. Gestão de Credenciais e Segurança no GitHub
- Os arquivos `firebase-service-account.json`, `*-firebase-adminsdk-*.json`, `.env` e quaisquer certificados/chaves estão estritamente incluídos no `.gitignore`.
- Nunca commite chaves de conta de serviço no repositório. Em ambientes como Render, Fly.io, Railway ou Cloud Run, armazene as credenciais como variável de ambiente (secret) codificada ou monte o arquivo com permissão restrita.

### 6. Regras de Segurança do Firestore (`firestore.rules`)
- As requisições diretas do Flutter/clientes ao Firestore devem seguir o princípio de isolamento estrito:
  - Documentos em `/usuarios/{userId}` e subcoleções `/usuarios/{userId}/notas/{notaId}` são restritos exclusivamente a `request.auth.uid == userId`.
  - Nenhuma leitura ou escrita global em `/notas` é permitida.
  - O arquivo `firestore.rules` foi adicionado à raiz do repositório para implantação no console Firebase (`firebase deploy --only firestore:rules`).

### 7. Permissões IAM da Conta de Serviço (Princípio do Menor Privilégio)
- A conta de serviço utilizada pela API deve possuir apenas os privilégios mínimos necessários:
  - **Papel Recomendado**: `Cloud Datastore User` (ou `roles/datastore.user`) para ler e gravar documentos no Firestore.
  - **Firebase Authentication**: A verificação de ID Tokens (`firebase_admin.auth.verify_id_token`) é feita via validação de assinatura de chave pública local e cacheada, **não** necessitando de papéis de escrita ou administração de usuários no IAM.
  - **Evitar**: Não atribua permissões como `Firebase Admin`, `Editor` ou `Owner` à conta de serviço em produção.

### 8. HTTPS e Proteção de Tráfego em Produção
- O Uvicorn roda atrás de um proxy reverso (Nginx, Traefik, Caddy, Cloudflare ou o roteador gerenciado da nuvem).
- Toda comunicação com o aplicativo Flutter deve ocorrer obrigatoriamente através de **HTTPS** (TLS 1.2+ / TLS 1.3).
- Utilize cabeçalhos `Strict-Transport-Security` (HSTS) no proxy reverso para impedir *downgrade attacks*.

