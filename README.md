# JediMindAgent

JediMindAgent - ИИ-ассистент для диагностики текущего состояния пользователя и подбора практик из книги «Путь джедая» с учетом контекста диалога.

Проект находится на ранней стадии. Сейчас реализован Docker-first FastAPI-каркас с PostgreSQL, Alembic и минимальным RAG-контуром через ChromaDB.

## Что уже есть

- минимальное FastAPI-приложение в `src/`;
- PostgreSQL в Docker Compose;
- Alembic и первая foundation-миграция;
- `GET /health` для проверки приложения;
- `GET /health/db` для проверки подключения к PostgreSQL;
- экспериментальный `POST /api/v1/ai/chat` для проверки OpenAI-compatible chat через LangChain;
- ChromaDB для RAG;
- ручной PDF ingestion в ChromaDB;
- локальные бесплатные embeddings через `sentence-transformers`;
- `POST /api/v1/rag/retrieve` для ручной проверки retrieval;
- продуктовая схема PostgreSQL: пользователи, состояние, история чата, упражнения, проверки готовности (миграция `0002_product_schema`);
- агент со structured output: диагностика состояния и предложение упражнений;
- тестовый веб-интерфейс без JavaScript на `http://localhost:8000/`.

## Локальный запуск

Запустить приложение, БД и ChromaDB:

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

Остановить контейнеры и удалить volumes PostgreSQL и ChromaDB:

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

RAG-настройки не хранятся в `.env`: не-секретные параметры локальной embedding-модели, ChromaDB collection и `top_k` зафиксированы в `src/jedi_mind_agent/rag/config.py`.

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

## Проверка RAG

PDF-источники нужно хранить локально в директории `data/sources/`. Эта директория исключена из git и Docker build context.

Пример ingestion одной книги:

```bash
docker compose exec app python -m jedi_mind_agent.rag.ingest /app/data/sources/example.pdf \
  --source-slug jedi-path \
  --source-title "Путь джедая" \
  --replace
```

Первый запуск локальной embedding-модели может занять время: модель скачивается и кэшируется в Docker volume `model_cache`.

Проверить retrieval без LLM:

```bash
curl -X POST http://localhost:8000/api/v1/rag/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"Как снизить перегруз перед работой?","top_k":5}'
```

Проверить chat с RAG-контекстом:

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Что из книги поможет при перегрузе?","use_rag":true}'
```

Отключить RAG для chat-запроса:

```bash
curl -X POST http://localhost:8000/api/v1/ai/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Помоги быстро оценить мое состояние","use_rag":false}'
```

По умолчанию `use_rag` равен `false`, чтобы обычная проверка chat endpoint не запускала локальную embedding-модель.

## Веб-интерфейс

Откройте `http://localhost:8000/`. Интерфейс рендерится на сервере (Jinja2 + HTML-формы), JavaScript не используется.

1. Создайте пользователя в шапке или выберите существующего.
2. Напишите в чат о своём состоянии — агент задаст уточняющие вопросы и заполнит панель «Состояние».
3. Когда уровень определён, агент предложит упражнение — оно появится справа.
4. Меняйте статус упражнения кнопками: принять → начать → выполнено.
5. После выполненного упражнения нажмите «Проверить готовность».

Галочка «искать в книге» подмешивает RAG-контекст из ChromaDB. Каждое действие перезагружает страницу; ответ агента занимает несколько секунд.

Правила, которые применяются в коде, а не в промпте:

- агент возвращает структурированный ответ, но в БД его пишет только доменный сервис `product/service.py`;
- из чата уровень можно установить только один раз, при первичной диагностике; дальше — только через проверку готовности;
- значения вне шкалы 1–10 отбрасываются;
- упражнения не предлагаются до определения уровня, одновременно активно не больше трёх;
- переходы статусов упражнений проверяются по фиксированной карте;
- проверка готовности без выполненных упражнений на текущем уровне не вызывает LLM и возвращает «пока не готов».

## Что планируется дальше

- улучшение chunking и качества retrieval (табы в тексте PDF, порог релевантности);
- тесты и линтер;
- SSE-стриминг ответа агента.
