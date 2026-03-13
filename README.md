# DUIMP - Consultas

> Sistema web para consulta automatizada de **DUIMP** (Declaração Única de Importação) via API REST do Portal Único Siscomex e processamento de **DI** (Declaração de Importação) via XML, com geração automática de planilhas Excel.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.0-092E20?logo=django&logoColor=white)
![Celery](https://img.shields.io/badge/Celery-5.3-37814A?logo=celery&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?logo=postgresql&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-1.25-009639?logo=nginx&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)

---

## Funcionalidades

- **Consulta DUIMP** — integração com API REST do Portal Único Siscomex (mTLS ou chave de acesso)
- **Processamento DI** — importação de XML exportado do Siscomex Importação
- **Excel automático** — geração de planilha formatada com 12 colunas (NCM, descrição, quantidade, valores, etc.)
- **Processamento assíncrono** — tarefas executadas em background via Celery + Redis
- **Monitoramento** — dashboard Flower para acompanhamento de tarefas em tempo real
- **Sistema de autenticação** — login, perfis (Admin / Operador / Consulta) e controle de permissões
- **Histórico e logs** — auditoria completa de consultas, erros e eventos do sistema
- **Criptografia** — chaves de acesso armazenadas com AES-256 (Fernet)
- **Certificado digital** — suporte a arquivo `.pfx` (A1) ou certificado instalado no Windows

---

## Arquitetura

```
                        ┌───────────┐
                   :80  │   Nginx   │  reverse proxy + static files
                        └─────┬─────┘
                              │
                 ┌────────────┼────────────┐
                 │            │            │
           ┌─────▼─────┐ ┌───▼───┐ ┌─────▼─────┐
           │  Gunicorn  │ │Flower │ │  Static/  │
           │  (Django)  │ │:5555  │ │  Media    │
           └─────┬──────┘ └───┬───┘ └───────────┘
                 │            │
          ┌──────▼──────┐     │
          │   Celery    │◄────┘
          │   Worker    │
          └──────┬──────┘
                 │
         ┌───────┼───────┐
         │               │
    ┌────▼────┐    ┌─────▼────┐
    │PostgreSQL│    │  Redis   │
    │  :5432   │    │  :6379   │
    └─────────┘    └──────────┘
```

| Serviço        | Responsabilidade                                  |
| -------------- | ------------------------------------------------- |
| **Nginx**      | Proxy reverso, serve arquivos estáticos e mídia   |
| **Gunicorn**   | Servidor WSGI — 3 workers para a aplicação Django |
| **Celery**     | Worker assíncrono para consultas DUIMP/DI         |
| **Flower**     | Dashboard de monitoramento do Celery              |
| **PostgreSQL** | Banco de dados relacional (produção)              |
| **Redis**      | Broker de mensagens e backend de resultados       |

---

## Stack Tecnológica

| Camada          | Tecnologia                                  |
| --------------- | ------------------------------------------- |
| Backend         | Python 3.12, Django 5.0.4                   |
| Tarefas         | Celery 5.3.6, Redis 7                       |
| Banco           | PostgreSQL 16 (Docker) / SQLite (dev local) |
| Servidor        | Gunicorn 22.0 + Nginx 1.25                  |
| Frontend        | Tailwind CSS (CDN) + Alpine.js              |
| Criptografia    | cryptography 42 (Fernet AES-256)            |
| Containerização | Docker + Docker Compose                     |

---

## Início Rápido (Docker)

> **Pré-requisitos:** Docker e Docker Compose instalados.

### 1. Clone o repositório

```bash
git clone https://github.com/seu-usuario/duimp-consultas.git
cd duimp-consultas
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
```

Edite o `.env` e preencha ao menos:

| Variável     | Descrição                                          |
| ------------ | -------------------------------------------------- |
| `SECRET_KEY` | Chave secreta do Django (string longa e aleatória) |
| `FERNET_KEY` | Chave AES-256 — gere com o comando abaixo          |

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. Suba os containers

```bash
docker compose up --build -d
```

### 4. Crie o superusuário

```bash
docker compose exec web python manage.py createsuperuser
```

### 5. Acesse o sistema

| URL                      | Descrição                     |
| ------------------------ | ----------------------------- |
| http://localhost         | Aplicação principal           |
| http://localhost/flower/ | Monitoramento Celery (Flower) |
| http://localhost/admin/  | Painel administrativo Django  |

> No primeiro acesso sem usuários, o sistema redireciona automaticamente para `/setup/` onde você cria o administrador.

---

## Desenvolvimento Local (sem Docker)

### Pré-requisitos

- Python 3.12+
- Redis rodando em `localhost:6379`

### Setup

```bash
# Criar e ativar ambiente virtual
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/macOS

# Instalar dependências
pip install -r requirements.txt

# Configurar variáveis de ambiente
cp .env.example .env
# Editar .env: SECRET_KEY, FERNET_KEY (DB_HOST vazio = usa SQLite)

# Aplicar migrações
python manage.py migrate

# Criar superusuário
python manage.py createsuperuser
```

### Executar (2 terminais)

```bash
# Terminal 1 — Django
python manage.py runserver

# Terminal 2 — Celery Worker
celery -A botduimp worker --loglevel=info --pool=solo   # Windows
celery -A botduimp worker --loglevel=info               # Linux/macOS
```

Acesse `http://127.0.0.1:8000/`

---

## Desenvolvimento Híbrido (recomendado no Windows)

> **Ideal para uso diário**: PostgreSQL + Redis rodam em Docker, enquanto Django + Celery rodam
> nativamente no Windows — permitindo acesso ao **repositório de certificados do Windows**.

```bash
# 1. Subir apenas a infraestrutura
docker compose up -d db redis

# 2. Configurar .env (porta 5433 evita conflito com PostgreSQL local)
#    DB_HOST=127.0.0.1
#    DB_PORT=5433

# 3. Aplicar migrações + criar admin
python manage.py migrate
python manage.py createsuperuser

# 4. Terminal 1 — Django
python manage.py runserver

# 5. Terminal 2 — Celery Worker
celery -A botduimp worker --loglevel=info --pool=solo
```

Neste modo, a opção **"Certificado instalado (Windows CurrentUser\My)"** na tela de
Nova Consulta lista automaticamente os certificados digitais da máquina.

---

## Autenticação no Portal Único Siscomex

O sistema oferece **três modos** de autenticação para consultas DUIMP:

### 1. Certificado A1 (.pfx)

Na tela **Nova Consulta**, faça upload do arquivo `.pfx` e informe a senha. O sistema extrai a chave privada e o certificado para autenticação mTLS com a API do Portal Único.

### 2. Certificado instalado no Windows

Se o certificado está instalado no Windows (`CurrentUser\My`), o sistema lista os certificados disponíveis e exporta temporariamente para mTLS. Requer que a chave privada seja exportável.

> ⚠️ Esse modo funciona apenas em desenvolvimento local no Windows, não dentro de containers Docker.

### 3. Chave de Acesso

1. Acesse [portalunico.siscomex.gov.br](https://portalunico.siscomex.gov.br) com seu certificado digital
2. Vá em **Perfil → Chaves de Acesso → Gerar nova chave**
3. Copie o **ID da chave** e a **Chave secreta**
4. No DUIMP - Consultas, acesse **Configurações** e preencha os campos

As chaves são criptografadas com **AES-256 (Fernet)** antes de serem salvas no banco.

---

## Perfis de Permissão

| Perfil       | Permissões                                             |
| ------------ | ------------------------------------------------------ |
| **Admin**    | Acesso total: usuários, configurações, logs, consultas |
| **Operador** | Cria e acompanha consultas, exporta Excel              |
| **Consulta** | Visualização e download de resultados                  |

Os perfis são criados automaticamente no setup inicial.

---

## Estrutura do Projeto

```
duimp-consultas/
├── botduimp/               # Configurações Django
│   ├── settings.py         #   Settings com PostgreSQL/SQLite dual-mode
│   ├── celery.py           #   Configuração Celery
│   ├── urls.py             #   Rotas principais
│   └── wsgi.py             #   Entrypoint WSGI
├── core/                   # Utilitários compartilhados
│   └── formatters.py       #   Formatação pt-BR (moeda, quantidade, %)
├── pucomex/                # Integração Portal Único Siscomex
│   ├── auth.py             #   Autenticação mTLS + chave de acesso
│   ├── api_duimp.py        #   Cliente REST API DUIMP
│   ├── normalizer.py       #   Normalização de respostas da API
│   └── windows_cert_store.py  # Acesso ao repositório Windows
├── declaracoes/            # App principal
│   ├── models.py           #   ConfiguracaoAPI, Consulta, Item, Log
│   ├── views.py            #   Views com autenticação e permissões
│   ├── tasks.py            #   Tasks Celery (DUIMP + DI)
│   ├── excel_export.py     #   Geração de Excel formatado
│   └── services_di.py      #   Parser XML para DI
├── templates/              # Templates HTML (Tailwind + Alpine.js)
├── nginx/                  # Configuração Nginx
│   └── default.conf        #   Reverse proxy + static files
├── Dockerfile              # Multi-stage build (builder + runtime)
├── docker-compose.yml      # 6 serviços com health checks
├── entrypoint.sh           # Startup: wait-for-db + migrate + collectstatic
├── requirements.txt        # Dependências Python
├── .env.example            # Template de variáveis de ambiente
└── .gitignore              # Arquivos ignorados pelo Git
```

---

## Comandos Úteis

```bash
# Ver logs de todos os serviços
docker compose logs -f

# Ver logs apenas do worker Celery
docker compose logs -f celery

# Acessar shell Django
docker compose exec web python manage.py shell

# Aplicar migrações manualmente
docker compose exec web python manage.py migrate

# Parar todos os serviços
docker compose down

# Parar e remover volumes (CUIDADO: apaga o banco)
docker compose down -v

# Rebuild após alterar código
docker compose up --build -d
```

---

## Variáveis de Ambiente

| Variável                | Padrão                              | Descrição                              |
| ----------------------- | ----------------------------------- | -------------------------------------- |
| `SECRET_KEY`            | —                                   | Chave secreta do Django (obrigatória)  |
| `DEBUG`                 | `False`                             | Modo debug                             |
| `ALLOWED_HOSTS`         | `localhost,127.0.0.1`               | Hosts permitidos                       |
| `CSRF_TRUSTED_ORIGINS`  | `http://localhost,http://127.0.0.1` | Origens confiáveis para CSRF           |
| `DB_NAME`               | `botduimp`                          | Nome do banco PostgreSQL               |
| `DB_USER`               | `botduimp`                          | Usuário PostgreSQL                     |
| `DB_PASSWORD`           | `botduimp_secret`                   | Senha PostgreSQL                       |
| `DB_HOST`               | _(vazio = SQLite)_                  | Host do banco (Docker: `db`)           |
| `DB_PORT`               | `5433`                              | Porta PostgreSQL (5433 evita conflito) |
| `CELERY_BROKER_URL`     | `redis://localhost:6379/0`          | URL do broker Redis                    |
| `CELERY_RESULT_BACKEND` | `redis://localhost:6379/0`          | URL do result backend Redis            |
| `FERNET_KEY`            | —                                   | Chave AES-256 Fernet (obrigatória)     |

---

## Segurança e Publicação

- Não publique o arquivo `.env`, bancos locais, dumps de depuração, certificados `.pfx/.pem` ou arquivos gerados em `media/`.
- Este repositório já está configurado para ignorar artefatos locais em `.gitignore` e `.dockerignore`.
- Para produção, mantenha `DEBUG=False` e habilite HTTPS com as variáveis `USE_HTTPS_IN_PRODUCTION`, `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` e `SECURE_HSTS_SECONDS`.
- Se houver proxy reverso na frente da aplicação, configure `SECURE_PROXY_SSL_HEADER` corretamente.
- O nome público do projeto é **DUIMP - Consultas**; o módulo Django interno permanece como `botduimp` por compatibilidade técnica.

---

## Licença

Projeto desenvolvido para fins de portfólio e demonstração de habilidades em desenvolvimento web com Python/Django.

---

## Excel gerado

O arquivo `.xlsx` contém as colunas:

| Nº Adição | Seq. | Quantidade | Unidade Medida | Descrição Mercadoria | cClassTrib | Valor Unitário | II  | IPI | PIS/PASEP | COFINS | NCM |
| --------- | ---- | ---------- | -------------- | -------------------- | ---------- | -------------- | --- | --- | --------- | ------ | --- |

Os valores monetários e percentuais seguem o formato brasileiro (vírgula decimal, ponto de milhar).
