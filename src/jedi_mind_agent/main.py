from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from jedi_mind_agent.api.v1.ai import router as ai_router
from jedi_mind_agent.api.v1.product import router as product_router
from jedi_mind_agent.api.v1.rag import router as rag_router
from jedi_mind_agent.core.config import get_settings
from jedi_mind_agent.db.health import check_database
from jedi_mind_agent.db.session import async_session, dispose_engine
from jedi_mind_agent.product.service import DEFAULT_USERNAME, get_or_create_user
from jedi_mind_agent.web.router import STATIC_DIR
from jedi_mind_agent.web.router import router as web_router


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Create the default user before serving, so concurrent first requests cannot race on it.
    async with async_session() as session:
        await get_or_create_user(session, DEFAULT_USERNAME)
    yield
    await dispose_engine()


settings = get_settings()

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(ai_router)
app.include_router(rag_router)
app.include_router(product_router)
app.include_router(web_router)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "env": settings.app_env}


@app.get("/health/db")
async def database_health() -> dict[str, str]:
    await check_database()
    return {"status": "ok", "database": "reachable"}
