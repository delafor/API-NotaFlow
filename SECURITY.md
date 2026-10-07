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

### 5. Gestão de Credenciais
- O arquivo `firebase-service-account.json` e chaves privadas estão estritamente incluídos no `.gitignore`.
