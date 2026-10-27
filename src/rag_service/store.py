"""Book chunks in PostgreSQL + pgvector.

The table `rag_chunks` is created by the Django migration `knowledge.0003_rag_chunks`; its columns are a contract
with this module. Chunks reference `rag_books` with ON DELETE CASCADE, so deleting a book in the admin removes them.

Search is an exact cosine scan without an ANN index: a level filter on top of an HNSW index may return fewer than
top_k rows, while an exact scan over a few books' chunks takes milliseconds and always respects the filter.
"""

from collections.abc import Sequence

import psycopg

from rag_service.schemas import RetrievalResult, TextChunk

INSERT_SQL = """
INSERT INTO rag_chunks (
    id, book_id, source_slug, source_title, source_filename, file_hash, chunk_index, chunk_hash,
    page_start, page_end, level, text, embedding_model, embedding
) VALUES (
    %(id)s, %(book_id)s, %(source_slug)s, %(source_title)s, %(source_filename)s, %(file_hash)s, %(chunk_index)s,
    %(chunk_hash)s, %(page_start)s, %(page_end)s, %(level)s, %(text)s, %(embedding_model)s, %(embedding)s::vector
)
"""


def replace_book_chunks(
    conn: psycopg.Connection,
    *,
    book_id: int,
    source_slug: str,
    source_title: str,
    source_filename: str,
    file_hash: str,
    embedding_model: str,
    chunks: Sequence[TextChunk],
    embeddings: Sequence[Sequence[float]],
) -> None:
    """Replace all chunks of the book. Call inside the caller's transaction, so readers never see a half-written book."""
    conn.execute("DELETE FROM rag_chunks WHERE book_id = %s", (book_id,))
    with conn.cursor() as cursor:
        cursor.executemany(
            INSERT_SQL,
            [
                {
                    "id": build_chunk_id(source_slug, chunk),
                    "book_id": book_id,
                    "source_slug": source_slug,
                    "source_title": source_title,
                    "source_filename": source_filename,
                    "file_hash": file_hash,
                    "chunk_index": chunk.chunk_index,
                    "chunk_hash": chunk.chunk_hash,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "level": chunk.level,
                    "text": chunk.text,
                    "embedding_model": embedding_model,
                    "embedding": to_vector_literal(vector),
                }
                for chunk, vector in zip(chunks, embeddings, strict=True)
            ],
        )


def query(
    conn: psycopg.Connection,
    *,
    query_embedding: Sequence[float],
    top_k: int,
    max_level: int | None = None,
    source_slug: str | None = None,
) -> list[RetrievalResult]:
    rows = conn.execute(
        """
        SELECT id, text, embedding <=> %(embedding)s::vector AS score,
               source_slug, source_title, source_filename, page_start, page_end, level
        FROM rag_chunks
        WHERE (%(max_level)s::int IS NULL OR level <= %(max_level)s::int)
          AND (%(source_slug)s::text IS NULL OR source_slug = %(source_slug)s::text)
        ORDER BY score
        LIMIT %(top_k)s
        """,
        {
            "embedding": to_vector_literal(query_embedding),
            "max_level": max_level,
            "source_slug": source_slug,
            "top_k": top_k,
        },
    ).fetchall()
    return [RetrievalResult(chunk_id=row.pop("id"), **row) for row in rows]


def stats(conn: psycopg.Connection) -> dict:
    row = conn.execute(
        "SELECT (SELECT extversion FROM pg_extension WHERE extname = 'vector') AS pgvector, "
        "(SELECT count(*) FROM rag_chunks) AS count"
    ).fetchone()
    return {"pgvector": row["pgvector"], "count": row["count"]}


def build_chunk_id(source_slug: str, chunk: TextChunk) -> str:
    return f"{source_slug}:{chunk.chunk_index}:{chunk.chunk_hash[:12]}"


def to_vector_literal(vector: Sequence[float]) -> str:
    # pgvector's text format; no client-side adapter (and no numpy in the query path) is needed.
    return "[" + ",".join(f"{value:.7g}" for value in vector) + "]"
