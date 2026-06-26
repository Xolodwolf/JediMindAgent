# JediMindAgent

JediMindAgent - ИИ-ассистент для диагностики текущего состояния пользователя и подбора практик из книги «Путь джедая» с учетом контекста диалога.

Проект находится на ранней стадии. Сейчас реализован первый технический шаг: Docker-first FastAPI-каркас с PostgreSQL и Alembic.

## Что уже есть

- минимальное FastAPI-приложение в `src/`;
- PostgreSQL в Docker Compose;
- Alembic и первая foundation-миграция;
- `GET /health` для проверки приложения;
- `GET /health/db` для проверки подключения к PostgreSQL.

## Локальный запуск

Запустить приложение и БД:

```bash
docker compose up --build
```

При старте контейнер приложения автоматически выполнит:

```bash
alembic upgrade head
```

Проверить приложение:

```bash
curl http://localhost:8000/health
```

Ожидаемый ответ:

```json
{"status":"ok","service":"JediMindAgent","env":"local"}
```

Проверить подключение к БД:

```bash
curl http://localhost:8000/health/db
```

Ожидаемый ответ:

```json
{"status":"ok","database":"reachable"}
```

Остановить контейнеры:

```bash
docker compose down
```

Остановить контейнеры и удалить volume PostgreSQL:

```bash
docker compose down -v
```

## Переменные окружения

Для локального Docker-запуска значения уже заданы в `docker-compose.yml`. Шаблон для ручной настройки находится в `.env.example`.

## Что планируется дальше

- подключение OpenAI API через сервисный слой;
- эксперименты с агентными инструкциями и structured outputs;
- PDF ingestion, embeddings и RAG через ChromaDB;
- продуктовая логика пользователей, упражнений и readiness checks после проверки AI/RAG-контура.
