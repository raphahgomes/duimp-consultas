# ============================================================================
# DUIMP - Consultas — Multi-stage Dockerfile
# ============================================================================

# ── Stage 1: Build (instala dependências + collectstatic) ──────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /build

RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime (imagem final enxuta) ─────────────────────────────────
FROM python:3.12-slim AS runtime

LABEL maintainer="raphael" \
    description="DUIMP - Consultas — Portal Único Siscomex" \
      version="1.0.0"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=botduimp.settings

WORKDIR /app

# Dependências de runtime apenas (libpq para PostgreSQL)
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copia pacotes Python do stage builder
COPY --from=builder /install /usr/local

# Copia código-fonte
COPY . .

# Cria diretórios necessários
RUN mkdir -p /app/staticfiles /app/media/excels

# Usuário não-root (segurança)
RUN addgroup --system botduimp \
    && adduser --system --ingroup botduimp botduimp \
    && chown -R botduimp:botduimp /app

# Collectstatic (precisa de SECRET_KEY dummy)
RUN SECRET_KEY=build-placeholder FERNET_KEY=build-placeholder \
    python manage.py collectstatic --noinput 2>/dev/null || true

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

USER botduimp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8000/login/ || exit 1

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "botduimp.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--worker-tmp-dir", "/dev/shm", \
     "--timeout", "120", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
