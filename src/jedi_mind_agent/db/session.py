from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from jedi_mind_agent.core.config import get_settings


settings = get_settings()

engine = create_async_engine(settings.database_url, pool_pre_ping=True)
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def dispose_engine() -> None:
    await engine.dispose()
