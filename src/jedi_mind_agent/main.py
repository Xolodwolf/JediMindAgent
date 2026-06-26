from contextlib import asynccontextmanager

from fastapi import FastAPI

from jedi_mind_agent.core.config import get_settings
from jedi_mind_agent.db.health import check_database
from jedi_mind_agent.db.session import dispose_engine


@asynccontextmanager
async def lifespan(_: FastAPI):
    yield
    await dispose_engine()


settings = get_settings()

app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name, "env": settings.app_env}


@app.get("/health/db")
async def database_health() -> dict[str, str]:
    await check_database()
    return {"status": "ok", "database": "reachable"}
