#!/bin/sh
# Start of the web container: migrations (unless the host runs them as a separate release step), the admin
# account from the environment, then gunicorn.
set -e

if [ "${RUN_MIGRATIONS:-true}" = "true" ]; then
    python manage.py migrate --noinput
fi
python manage.py ensure_superuser

exec gunicorn jedi_mind_agent.wsgi:application \
    --bind "0.0.0.0:${PORT:-8000}" \
    --workers "${GUNICORN_WORKERS:-1}" \
    --threads "${GUNICORN_THREADS:-8}" \
    --timeout 120 \
    --access-logfile -
