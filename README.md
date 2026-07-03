# JediMindAgent

JediMindAgent - ИИ-ассистент для диагностики текущего состояния пользователя и подбора практик из книги «Путь джедая» с учетом контекста диалога.

Проект находится на ранней стадии. Сейчас реализован первый технический шаг: Docker-first FastAPI-каркас с PostgreSQL и Alembic.

## Что уже есть

- минимальное FastAPI-приложение в `src/`;
- PostgreSQL в Docker Compose;
- Alembic и первая foundation-миграция;
- `GET /health` для проверки приложения;
- `GET /health/db` для проверки подключения к PostgreSQL;
- экспериментальный `POST /api/v1/ai/chat` для проверки OpenAI-compatible chat через LangChain.

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

Для локального Docker-запуска используется файл `.env`. Шаблон для ручной настройки находится в `.env.example`.

Минимальная настройка `.env`:

```env
APP_NAME=JediMindAgent
APP_ENV=local
DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/jedi_mind_agent
OPENAI_API_KEY=sk-your-key
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_BASE_URL=https://api.openai.com/v1
```

AI-интеграция использует LangChain `ChatOpenAI`. Для OpenAI-compatible провайдера поменяйте `OPENAI_BASE_URL` и модель в `.env`.

После изменения `.env` перезапустите контейнер:

```bash
docker compose up --build
```

## Проверка OpenAI API

Запрос:

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Помоги быстро оценить мое состояние перед работой"}'
```

Если `OPENAI_API_KEY` задан корректно, ответ придет через LangChain `ChatOpenAI`. Если ключ не задан или API недоступен, endpoint вернет управляемый fallback с `used_fallback: true`.

Пример fallback-ответа:

```json
{
  "answer": "OpenAI API сейчас недоступен для приложения...",
  "model": "gpt-4.1-mini",
  "used_fallback": true
}
```

## Что планируется дальше

- эксперименты с агентными инструкциями и structured outputs;
- PDF ingestion, embeddings и RAG через ChromaDB;
- продуктовая логика пользователей, упражнений и readiness checks после проверки AI/RAG-контура.
