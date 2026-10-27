from functools import lru_cache

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from rag_service.config import DATABASE_URL, DB_POOL_MAX_SIZE


def libpq_dsn(url: str) -> str:
    """Django-style URLs may carry a driver suffix (postgresql+psycopg://); libpq wants the bare scheme."""
    scheme, rest = url.split("://", 1)
    return f"{scheme.split('+')[0]}://{rest}"


@lru_cache(maxsize=1)
def get_pool() -> ConnectionPool:
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not set: book jobs and chunks are stored in PostgreSQL.")
    return ConnectionPool(
        libpq_dsn(DATABASE_URL),
        min_size=1,
        max_size=DB_POOL_MAX_SIZE,
        kwargs={"autocommit": True, "row_factory": dict_row},
        open=True,
    )
