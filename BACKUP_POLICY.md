# Política e Procedimento de Backup & Recuperação — NotaFlow

Este documento estabelece a política gratuita, os objetivos de recuperação, a periodicidade e os procedimentos operacionais para backup e restauração dos dados do **Firestore** da aplicação NotaFlow.

---

## 🎯 1. Objetivos de Recuperação (RPO e RTO)

* **RPO (Recovery Point Objective — Perda Máxima Tolerável de Dados)**:
  * **24 horas** em regime diário padrão.
  * **6 horas** em períodos de alto volume ou pós-fechamento mensal.
  * *Significado*: Em caso de falha catastrófica ou exclusão acidental, o volume máximo de dados perdidos não excederá as alterações das últimas 24 horas.
* **RTO (Recovery Time Objective — Tempo Máximo Aceitável de Recuperação)**:
  * **30 minutos**.
  * *Significado*: A execução do script de restauração atômica em lotes recupera todo o estado funcional do Firestore em menos de meia hora.

---

## 📅 2. Periodicidade e Regra de Backup Gratuita

### Regra do Backup 3-2-1 (Sem Custos Adicionais)
1. **3 Cópias dos Dados**: Banco original no Firestore + Cópia local no disco + Cópia em mídia externa/dispositivo próprio secundário.
2. **2 Mídias Diferentes**: Armazenamento em nuvem (Firestore) e armazenamento em disco rígido / pen drive / outro computador pessoal.
3. **1 Cópia Offsite**: Armazenamento em nuvem pessoal ou pendrive guardado em local separado.

### Frequência Recomendada:
* **Frequência Diária / Semanal**: Conforme o fluxo de novos usuários e notas fiscais importadas.
* **Antes de deploys ou manutenções críticas**: Executar o backup manual preventivo.

---

## 🔐 3. Segurança e Criptografia

* **Isolamento de Credenciais**:
  * Os arquivos gerados **nunca** contêm credenciais de API, senhas do Firebase ou arquivos `.env`.
  * Os backups devem ser gravados em pasta **fora do repositório Git** (ex: `C:\Users\<usuario>\notaflow-backups` ou `../notaflow-backups`).
* **Criptografia Simétrica Forte**:
  * O script `scripts/backup_firestore.py` suporta criptografia com algoritmo **AES (Fernet)** e derivação de chave **PBKDF2HMAC-SHA256 com 100.000 iterações**.
  * O arquivo resultante possui extensão `.enc` e só pode ser lido fornecendo a senha mestra.

---

## 🛠️ 4. Como Executar o Backup

### Execução Simples (JSON puro em pasta externa):
```bash
python scripts/backup_firestore.py
```
*Por padrão, salva na pasta `../notaflow-backups/`.*

### Execução com Criptografia e Pasta Personalizada:
```powershell
$env:BACKUP_OUTPUT_DIR = "D:\MeusBackups\NotaFlow"
$env:BACKUP_ENCRYPTION_PASSWORD = "SuaSenhaSeguraAqui"
python scripts/backup_firestore.py
```

O arquivo gerado conterá metadados de versão e timestamp:
`notaflow_backup_20261013_140000.enc` (ou `.json`).

---

## ♻️ 5. Como Executar a Restauração (Procedimento de Disaster Recovery)

### Passo 1: Testar ou Restaurar
Para restaurar em um projeto de produção ou ambiente de homologação/teste:
```bash
python scripts/restore_firestore.py "D:\MeusBackups\NotaFlow\notaflow_backup_20261013_140000.enc" "SuaSenhaSeguraAqui"
```

### Passo 2: Verificação de Integridade
O script realiza restauração atômica em lotes (Firestore Batched Writes de até 400 documentos por lote) e exibe:
- Total de usuários restaurados.
- Total de notas fiscais restauradas.
- Timestamp de criação do backup.

---

## ⏰ 6. Lembrete / Automação Gratuita

Para não depender da memória humana, configure um agendamento gratuito:

### No Windows (Agendador de Tarefas / Task Scheduler):
1. Abra o **Agendador de Tarefas** (`taskschd.msc`).
2. Crie uma Tarefa Básica: *"NotaFlow Firestore Backup Semanal"*.
3. Disparador: **Semanalmente** (ex: todo domingo às 23:00).
4. Ação: **Iniciar um programa**:
   - Programa: `powershell.exe`
   - Argumentos: `-ExecutionPolicy Bypass -Command "& 'E:\Programacao\API-NotaFlow\backend\venv\Scripts\python.exe' 'E:\Programacao\API-NotaFlow\scripts\backup_firestore.py'"`

### No Linux/macOS (Cron):
```cron
0 23 * * 0 /caminho/venv/bin/python /caminho/scripts/backup_firestore.py >> /var/log/notaflow_backup.log 2>&1
```

---

## 🔍 7. Verificação Periódica de Leitura
Execute mensalmente a validação dos arquivos de backup existentes rodando o teste automatizado:
```bash
python tests/test_backup.py
```
Isso garante que a chave, o algoritmo de descriptografia e a estrutura JSON permanecem 100% íntegros e compatíveis com a versão atual da API.

