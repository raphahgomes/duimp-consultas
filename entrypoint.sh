#!/bin/sh
set -e

# ── Aguarda PostgreSQL (se DB_HOST estiver configurado) ────────────────────
if [ -n "$DB_HOST" ]; then
    echo "==> Aguardando PostgreSQL em $DB_HOST:${DB_PORT:-5432}..."
    until python -c "
import socket, os, sys
host = os.environ.get('DB_HOST', 'db')
port = int(os.environ.get('DB_PORT', 5432))
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.settimeout(2)
    s.connect((host, port))
    sys.exit(0)
except Exception:
    sys.exit(1)
finally:
    s.close()
" 2>/dev/null; do
        echo "    PostgreSQL indisponível — tentando novamente em 2s..."
        sleep 2
    done
    echo "==> PostgreSQL disponível!"
fi

# Migrações e collectstatic apenas no container web (evita race condition)
if [ "${RUN_MIGRATIONS:-false}" = "true" ]; then
    echo "==> Aplicando migrações..."
    python manage.py migrate --noinput

    echo "==> Coletando arquivos estáticos..."
    python manage.py collectstatic --noinput 2>/dev/null || true
fi

echo "==> Iniciando: $@"
exec "$@"
