# Web: Django + gunicorn. Deliberately light: no torch, no ChromaDB, no PDF parsing.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    DJANGO_SETTINGS_MODULE=jedi_mind_agent.settings \
    DJANGO_STATIC_ROOT=/app/staticfiles \
    DJANGO_MEDIA_ROOT=/app/media

WORKDIR /app

# The same uid as in the RAG image: both write to the shared media volume.
RUN useradd --uid 1000 --create-home app && mkdir -p /app/media && chown app /app/media

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY manage.py ./
COPY src/jedi_mind_agent ./src/jedi_mind_agent
COPY tests ./tests
RUN DJANGO_SECRET_KEY=collectstatic python manage.py collectstatic --noinput

USER app
EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py ensure_superuser && exec gunicorn jedi_mind_agent.wsgi:application --bind 0.0.0.0:8000 --workers 2 --threads 8 --timeout 120 --access-logfile -"]
