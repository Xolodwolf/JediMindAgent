from sqlalchemy import text

from jedi_mind_agent.db.session import async_session


async def check_database() -> None:
    async with async_session() as session:
        await session.execute(text("select 1"))
