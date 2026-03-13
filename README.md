# DUIMP - Consultas

Sistema web para consulta automatizada de **DUIMP** (Declaração Única de Importação) via API REST do Portal Único Siscomex e processamento de **DI** (Declaração de Importação) via XML, com geração automática de planilhas Excel.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092E20?logo=django&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## O que é

Aplicação Django que integra com a **API REST do Portal Único Siscomex** para consultar DUIMPs em lote, processar XMLs de DI e exportar os resultados em planilha Excel formatada com valores tributários (II, IPI, PIS/COFINS, NCM). Suporta autenticação via certificado digital A1, certificado instalado no Windows ou chave de acesso da API.

---

## Funcionalidades

- **Consulta DUIMP** — integração com API REST do Portal Único Siscomex (mTLS ou chave de acesso)
- **Processamento DI** — importação de XML exportado do Siscomex Importação
- **Excel automático** — planilha com 12 colunas: adição, NCM, descrição, quantidade, valores tributários e unitário
- **Processamento assíncrono** — tarefas em background via Celery + Redis
- **Monitoramento** — dashboard Flower para acompanhamento das tarefas em tempo real
- **Autenticação e perfis** — login, papéis (Admin / Operador / Consulta) e controle de permissões
- **Histórico e logs** — auditoria completa de consultas, erros e eventos do sistema
- **Criptografia** — chaves de acesso armazenadas com AES-256 (Fernet)

---

## Como Usar

### Pré-requisitos

- Docker e Docker Compose instalados

### Início Rápido

```bash
# 1. Clonar
git clone https://github.com/raphahgomes/duimp-consultas.git
cd duimp-consultas

# 2. Configurar variáveis de ambiente
cp .env.example .env
# Preencha SECRET_KEY e FERNET_KEY no .env

# Gerar FERNET_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# 3. Subir os containers
docker compose up --build -d

# 4. Criar superusuário
docker compose exec web python manage.py createsuperuser
```

No primeiro acesso, o sistema redireciona para `/setup/` onde você cria o administrador.

| URL | Descrição |
|-----|-----------|
| http://localhost | Aplicação principal |
| http://localhost/flower/ | Monitoramento Celery |
| http://localhost/admin/ | Painel administrativo |

### Desenvolvimento Local (sem Docker)

Requer Python 3.12+ e Redis em `localhost:6379`.

```bash
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # Linux/macOS
pip install -r requirements.txt
cp .env.example .env       # DB_HOST vazio = usa SQLite
python manage.py migrate
python manage.py createsuperuser

# Terminal 1
python manage.py runserver

# Terminal 2
celery -A botduimp worker --loglevel=info --pool=solo   # Windows
celery -A botduimp worker --loglevel=info               # Linux/macOS
```

> No Windows, rodar Django e Celery nativamente (em vez de Docker) permite usar certificados instalados diretamente no repositório `CurrentUser\My`.



---

## Autenticação no Portal Único

| Modo | Como usar |
|------|-----------|
| **Certificado A1 (.pfx)** | Upload do arquivo + senha na tela Nova Consulta |
| **Certificado Windows** | Seleciona o certificado instalado em `CurrentUser\My` — apenas Windows nativo, fora de container |
| **Chave de Acesso** | ID + chave secreta gerados em Perfil → Chaves de Acesso no Portal Único |

As chaves de acesso são criptografadas com AES-256 (Fernet) antes de serem salvas.

---

## Perfis de Permissão

| Perfil | Permissões |
|--------|-----------|
| **Admin** | Acesso total: usuários, configurações, logs e consultas |
| **Operador** | Cria e acompanha consultas, exporta Excel |
| **Consulta** | Visualização e download de resultados |

---

## Estrutura do Projeto

```
duimp-consultas/
├── botduimp/          # Configurações Django (settings, celery, urls, wsgi)
├── core/              # Utilitários compartilhados (formatação pt-BR)
├── pucomex/           # Integração Portal Único — auth, API DUIMP, mTLS Windows
├── declaracoes/       # App principal (models, views, tasks, excel_export)
├── templates/         # Templates HTML (Tailwind + Alpine.js)
├── nginx/             # Configuração do proxy reverso
├── Dockerfile
├── docker-compose.yml
├── entrypoint.sh      # wait-for-db + migrate + collectstatic
└── .env.example
```

---

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|----------|
| `SECRET_KEY` | — | Chave secreta do Django (obrigatória) |
| `DEBUG` | `False` | Modo debug |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Hosts permitidos |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost` | Origens CSRF confiáveis |
| `DB_NAME` | `botduimp` | Nome do banco PostgreSQL |
| `DB_USER` | `botduimp` | Usuário PostgreSQL |
| `DB_PASSWORD` | `botduimp_secret` | Senha PostgreSQL |
| `DB_HOST` | _(vazio = SQLite)_ | Host do banco |
| `DB_PORT` | `5433` | Porta PostgreSQL |
| `CELERY_BROKER_URL` | `redis://localhost:6379/0` | Broker Redis |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0` | Result backend Redis |
| `FERNET_KEY` | — | Chave AES-256 Fernet (obrigatória) |

---

## Implantação

Use `.env.example` como base. Em produção:

- Mantenha `DEBUG=False`.
- Habilite HTTPS via `USE_HTTPS_IN_PRODUCTION`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` e `SECURE_HSTS_SECONDS`.
- Configure `SECURE_PROXY_SSL_HEADER` se a aplicação estiver atrás de proxy reverso.

---

## Stack

| Camada | Tecnologia |
|--------|----------|
| Backend | Python 3.12, Django 5.0.4 |
| Tarefas | Celery 5.3.6 + Redis 7 |
| Banco | PostgreSQL 16 / SQLite (dev) |
| Servidor | Gunicorn + Nginx 1.25 |
| Frontend | Tailwind CSS + Alpine.js |
| Criptografia | Fernet AES-256 |
| Deploy | Docker + Docker Compose |

---

## Licença

Distribuído sob a licença MIT. Veja [LICENSE](LICENSE).

---

## Autor

Desenvolvido por **Raphael Gomes** — [GitHub](https://github.com/raphahgomes)
